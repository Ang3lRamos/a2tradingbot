from tradebot.publish import role_url


def test_role_url_keeps_supabase_project_suffix():
    pooler = "postgresql://postgres.abc123:secreto@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    assert role_url(pooler, "dashboard_reader", "p@ss") == \
        "postgresql://dashboard_reader.abc123:p%40ss@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    assert role_url("postgresql://postgres:x@localhost/db", "dashboard_operator", "y") == \
        "postgresql://dashboard_operator:y@localhost/db"
