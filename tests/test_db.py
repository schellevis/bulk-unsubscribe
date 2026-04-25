from sqlalchemy import text

from app.db import Base, get_session_factory


def test_session_factory_yields_working_session(tmp_path):
    SessionLocal = get_session_factory(f"sqlite:///{tmp_path}/test.db")

    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_base_metadata_is_empty_until_models_imported():
    assert hasattr(Base, "metadata")
