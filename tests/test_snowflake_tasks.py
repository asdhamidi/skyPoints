"""
Tests for airflow/scripts/snowflake_tasks.py — the DAG's business logic,
extracted so it's testable without Airflow itself importable (see
airflow/dags/skypoints_daily_pipeline.py, which just wires these into tasks).

Snowflake connections are mocked throughout (patching get_snowflake_connection
itself) rather than requiring snowflake-connector-python to be installed or a
live account — only the pure SQL/path-building logic and the private-key
loading (via the cryptography library, a real dependency here) are exercised
directly.
"""
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import snowflake_tasks as tasks


def _write_test_key(tmp_path, passphrase: bytes | None = None):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    key_path = tmp_path / "test_key.p8"
    key_path.write_bytes(pem)
    return key_path


class TestLoadPrivateKey:
    def test_loads_unencrypted_key(self, tmp_path):
        key_path = _write_test_key(tmp_path)
        result = tasks.load_private_key(str(key_path))
        assert isinstance(result, bytes)
        # round-trip: the returned DER/PKCS8 bytes must themselves be loadable
        reloaded = serialization.load_der_private_key(result, password=None)
        assert reloaded.key_size == 2048

    def test_loads_encrypted_key_with_passphrase(self, tmp_path):
        key_path = _write_test_key(tmp_path, passphrase=b"s3cret")
        result = tasks.load_private_key(str(key_path), passphrase="s3cret")
        reloaded = serialization.load_der_private_key(result, password=None)
        assert reloaded.key_size == 2048

    def test_wrong_passphrase_raises_helpful_error(self, tmp_path):
        key_path = _write_test_key(tmp_path, passphrase=b"s3cret")
        with pytest.raises(ValueError) as exc_info:
            tasks.load_private_key(str(key_path), passphrase="wrong")
        assert str(key_path) in str(exc_info.value)

    def test_garbage_file_raises_helpful_error(self, tmp_path):
        bad_path = tmp_path / "not_a_key.p8"
        bad_path.write_text("this is not a PEM file")
        with pytest.raises(ValueError) as exc_info:
            tasks.load_private_key(str(bad_path))
        assert "Could not load private key" in str(exc_info.value)
        assert str(bad_path) in str(exc_info.value)

    def test_public_key_file_raises_error_naming_the_actual_problem(self, tmp_path):
        # Pointing SNOWFLAKE_PRIVATE_KEY_PATH at the .pub file instead of the
        # private key is a real, easy mistake — the error should say so.
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pub_path = tmp_path / "key.pub"
        pub_path.write_bytes(public_pem)
        with pytest.raises(ValueError) as exc_info:
            tasks.load_private_key(str(pub_path))
        assert "PUBLIC KEY" in str(exc_info.value)

    def test_empty_file_raises_helpful_error(self, tmp_path):
        empty_path = tmp_path / "empty.p8"
        empty_path.write_bytes(b"")
        with pytest.raises(ValueError) as exc_info:
            tasks.load_private_key(str(empty_path))
        assert "empty file" in str(exc_info.value)


class TestBuildSql:
    def test_build_put_sql(self):
        sql = tasks.build_put_sql("/opt/airflow/landing/aus_member_20240115.csv", "RAW.MEMBER_PROFILE_STAGE")
        assert "PUT file:///opt/airflow/landing/aus_member_20240115.csv" in sql
        assert "@RAW.MEMBER_PROFILE_STAGE" in sql
        assert "AUTO_COMPRESS = TRUE" in sql

    def test_build_copy_into_csv_sql_shape(self):
        sql = tasks.build_copy_into_csv_sql(
            "RAW.AUS_MEMBER_PROFILE", "RAW.MEMBER_PROFILE_STAGE", tasks.AUS_COLUMNS, "aus_member_20240115.csv"
        )
        assert "COPY INTO RAW.AUS_MEMBER_PROFILE" in sql
        assert (
            "unique_id, member_name, tier_type, date_of_birth, date_of_enrollment, "
            "date_of_flight, source_file_name" in sql
        )
        assert "$1, $2, $3, $4, $5, $6, METADATA$FILENAME" in sql
        assert "PATTERN = '.*aus_member_20240115.csv.*'" in sql
        assert "FORMAT_NAME = RAW.CSV_FORMAT" in sql

    def test_build_copy_into_csv_sql_select_list_matches_column_count(self):
        for columns in (tasks.AUS_COLUMNS, tasks.IND_COLUMNS, tasks.USA_COLUMNS):
            sql = tasks.build_copy_into_csv_sql("T", "S", columns, "f.csv")
            expected_select = ", ".join(f"${i + 1}" for i in range(len(columns))) + ", METADATA$FILENAME"
            assert expected_select in sql

    def test_build_copy_into_json_sql(self):
        sql = tasks.build_copy_into_json_sql("redemption_20240115.json")
        assert "COPY INTO RAW.REDEMPTION_FEED (payload, source_file_name)" in sql
        assert "PATTERN = '.*redemption_20240115.json.*'" in sql
        assert "FORMAT_NAME = RAW.JSON_FORMAT" in sql


class TestFilePaths:
    def test_member_file_path(self):
        assert (
            tasks.member_file_path("/opt/airflow/landing", "aus", "20240115", "csv")
            == "/opt/airflow/landing/aus_member_20240115.csv"
        )

    def test_redemption_file_path(self):
        assert (
            tasks.redemption_file_path("/opt/airflow/landing", "20240115")
            == "/opt/airflow/landing/redemption_20240115.json"
        )


class TestPutAndCopyCsv:
    def test_executes_put_then_copy(self):
        cur = MagicMock()
        tasks.put_and_copy_csv(
            cur, "/landing/aus_member_20240115.csv", "RAW.MEMBER_PROFILE_STAGE",
            "RAW.AUS_MEMBER_PROFILE", tasks.AUS_COLUMNS,
        )
        assert cur.execute.call_count == 2
        put_sql, copy_sql = (c.args[0] for c in cur.execute.call_args_list)
        assert put_sql.startswith("PUT file://")
        assert "COPY INTO RAW.AUS_MEMBER_PROFILE" in copy_sql


class TestStageAndCopyTasks:
    @patch("snowflake_tasks.get_snowflake_connection")
    def test_stage_and_copy_aus_executes_expected_sql(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        tasks.stage_and_copy_aus("/opt/airflow/landing", "20240115")

        executed = [c.args[0] for c in mock_conn.cursor.return_value.execute.call_args_list]
        assert any("aus_member_20240115.csv" in s for s in executed)
        assert any("RAW.AUS_MEMBER_PROFILE" in s for s in executed)
        mock_conn.close.assert_called_once()

    @patch("snowflake_tasks.get_snowflake_connection")
    def test_stage_and_copy_closes_connection_even_on_error(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.execute.side_effect = RuntimeError("boom")
        mock_get_conn.return_value = mock_conn

        with pytest.raises(RuntimeError):
            tasks.stage_and_copy_aus("/opt/airflow/landing", "20240115")

        mock_conn.close.assert_called_once()

    @patch("snowflake_tasks.get_snowflake_connection")
    def test_stage_and_copy_ind_uses_ind_table_and_columns(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        tasks.stage_and_copy_ind("/opt/airflow/landing", "20240115")

        executed = [c.args[0] for c in mock_conn.cursor.return_value.execute.call_args_list]
        assert any("ind_member_20240115.csv" in s for s in executed)
        assert any("RAW.IND_MEMBER_PROFILE" in s and "individual_or_corporate" in s for s in executed)

    @patch("snowflake_tasks.get_snowflake_connection")
    def test_stage_and_copy_usa_uses_usa_table_and_columns(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        tasks.stage_and_copy_usa("/opt/airflow/landing", "20240115")

        executed = [c.args[0] for c in mock_conn.cursor.return_value.execute.call_args_list]
        assert any("usa_member_20240115.csv" in s for s in executed)
        assert any("RAW.USA_MEMBER_PROFILE" in s for s in executed)

    @patch("snowflake_tasks.get_snowflake_connection")
    def test_stage_and_copy_redemptions(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        tasks.stage_and_copy_redemptions("/opt/airflow/landing", "20240115")

        executed = [c.args[0] for c in mock_conn.cursor.return_value.execute.call_args_list]
        assert any("REDEMPTION_STAGE" in s for s in executed)
        assert any("RAW.REDEMPTION_FEED" in s for s in executed)
        mock_conn.close.assert_called_once()


class TestConvertAusXlsx:
    def test_calls_converter_and_produces_csv(self, tmp_path):
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.append(["Unique ID", "Member Name"])
        wb.active.append([1, "Mike"])
        wb.save(tmp_path / "aus_member_20240115.xlsx")

        tasks.convert_aus_xlsx(str(tmp_path), "20240115")

        assert (tmp_path / "aus_member_20240115.csv").exists()


class TestPublishRunSummary:
    @patch("snowflake_tasks.get_snowflake_connection")
    def test_queries_country_reference_and_match_status(self, mock_get_conn):
        mock_cur = MagicMock()
        mock_cur.fetchall.side_effect = [
            [("AUS",), ("IND",), ("USA",)],
            [("RESOLVED", 1), ("AMBIGUOUS", 1), ("ORPHAN", 1)],
            [("INVALID_ENROLLMENT_DATE", 2), ("MISSING_MEMBER_NAME", 1)],
        ]
        mock_cur.fetchone.return_value = (3,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        tasks.publish_run_summary()

        mock_get_conn.assert_called_once_with(role="SKYPOINTS_TRANSFORMER", warehouse="TRANSFORM_WH")
        executed = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any("rejected_member_records" in s for s in executed)
        mock_conn.close.assert_called_once()
