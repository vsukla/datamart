from unittest.mock import MagicMock
from compute_aggregates import _metric_union, _sql_rankings, _sql_yoy, compute


class TestMetricUnion:
    def test_single_metric_has_no_union_all(self):
        sql = _metric_union(["median_income"])
        assert "UNION ALL" not in sql

    def test_two_metrics_has_one_union_all(self):
        sql = _metric_union(["median_income", "pct_poverty"])
        assert sql.count("UNION ALL") == 1

    def test_n_metrics_has_n_minus_one_union_all(self):
        metrics = ["median_income", "pct_bachelors", "pct_poverty"]
        sql = _metric_union(metrics)
        assert sql.count("UNION ALL") == 2

    def test_metric_name_appears_as_literal(self):
        sql = _metric_union(["median_income"])
        assert "'median_income'" in sql

    def test_metric_column_cast_to_numeric(self):
        sql = _metric_union(["median_income"])
        assert "median_income::numeric" in sql

    def test_includes_state_fips(self):
        assert "state_fips" in _metric_union(["median_income"])

    def test_includes_geo_type(self):
        assert "geo_type" in _metric_union(["median_income"])

    def test_all_metric_names_present(self):
        metrics = ["median_income", "pct_bachelors", "median_home_value"]
        sql = _metric_union(metrics)
        for m in metrics:
            assert m in sql


class TestSqlRankings:
    def test_inserts_into_agg_rankings(self):
        assert "INSERT INTO agg_rankings" in _sql_rankings(["median_income"])

    def test_uses_rank_window_function(self):
        assert "RANK() OVER" in _sql_rankings(["median_income"])

    def test_uses_percent_rank_window_function(self):
        assert "PERCENT_RANK() OVER" in _sql_rankings(["median_income"])

    def test_partitions_by_geo_type_year_metric(self):
        sql = _sql_rankings(["median_income"])
        assert "PARTITION BY geo_type, year, metric" in sql

    def test_selects_peer_count(self):
        assert "peer_count" in _sql_rankings(["median_income"])

    def test_embeds_metric_union(self):
        sql = _sql_rankings(["pct_poverty"])
        assert "pct_poverty" in sql

    def test_casts_percent_rank_to_numeric(self):
        # ROUND requires numeric; double precision must be cast first
        assert "::numeric" in _sql_rankings(["median_income"])


class TestSqlYoY:
    def test_inserts_into_agg_yoy(self):
        assert "INSERT INTO agg_yoy" in _sql_yoy(["median_income"])

    def test_joins_on_year_minus_one(self):
        assert "curr.year - 1" in _sql_yoy(["median_income"])

    def test_joins_on_fips(self):
        assert "prev.fips" in _sql_yoy(["median_income"])

    def test_joins_on_metric(self):
        assert "prev.metric" in _sql_yoy(["median_income"])

    def test_computes_change_abs(self):
        assert "change_abs" in _sql_yoy(["median_income"])

    def test_computes_change_pct(self):
        assert "change_pct" in _sql_yoy(["median_income"])

    def test_uses_nullif_to_guard_division(self):
        assert "NULLIF" in _sql_yoy(["median_income"])

    def test_embeds_metric_union(self):
        sql = _sql_yoy(["pct_bachelors"])
        assert "pct_bachelors" in sql


class TestCompute:
    def _make_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cur

    def test_truncates_tables_first(self):
        conn, cur = self._make_conn()
        compute(conn)
        first_sql = cur.execute.call_args_list[0][0][0]
        assert "TRUNCATE" in first_sql

    def test_truncates_all_four_tables(self):
        conn, cur = self._make_conn()
        compute(conn)
        truncate_sql = cur.execute.call_args_list[0][0][0]
        for table in ("agg_national_summary", "agg_state_summary", "agg_rankings", "agg_yoy"):
            assert table in truncate_sql

    def test_five_execute_calls_total(self):
        # 1 TRUNCATE + 4 INSERTs
        conn, cur = self._make_conn()
        compute(conn)
        assert cur.execute.call_count == 5

    def test_national_summary_inserted_second(self):
        conn, cur = self._make_conn()
        compute(conn)
        sql = cur.execute.call_args_list[1][0][0]
        assert "agg_national_summary" in sql

    def test_state_summary_inserted_third(self):
        conn, cur = self._make_conn()
        compute(conn)
        sql = cur.execute.call_args_list[2][0][0]
        assert "agg_state_summary" in sql

    def test_rankings_inserted_fourth(self):
        conn, cur = self._make_conn()
        compute(conn)
        sql = cur.execute.call_args_list[3][0][0]
        assert "agg_rankings" in sql

    def test_yoy_inserted_last(self):
        conn, cur = self._make_conn()
        compute(conn)
        sql = cur.execute.call_args_list[4][0][0]
        assert "agg_yoy" in sql
