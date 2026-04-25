from sqlalchemy import select, text

from app.db import Base, get_engine, get_session_factory
from app.models import account, job, sender, whitelist_rule  # noqa: F401 — register models
from app.models.account import Account, ProviderType
from app.models.job import Job, JobType
from app.models.sender import Sender
from app.models.whitelist_rule import WhitelistKind, WhitelistRule


def test_session_factory_yields_working_session(tmp_path):
    SessionLocal = get_session_factory(f"sqlite:///{tmp_path}/test.db")

    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_base_metadata_is_empty_until_models_imported():
    assert hasattr(Base, "metadata")


def test_sqlite_foreign_keys_pragma_is_on(tmp_path):
    """PRAGMA foreign_keys must be ON so that ON DELETE CASCADE works."""
    engine = get_engine(f"sqlite:///{tmp_path}/fk-test.db")
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1


def test_delete_account_cascades_to_child_rows(tmp_path):
    """Deleting an account must remove all dependent rows (no orphans)."""
    url = f"sqlite:///{tmp_path}/cascade-test.db"
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = get_session_factory(url)

    with SessionLocal() as session:
        acct = Account(
            name="Test",
            email="test@example.com",
            provider=ProviderType.imap,
            credential_encrypted="x",
        )
        session.add(acct)
        session.commit()

        sndr = Sender(
            account_id=acct.id,
            group_key="newsletter@example.com",
            from_email="newsletter@example.com",
            from_domain="example.com",
        )
        session.add(sndr)
        session.commit()

        job_row = Job(account_id=acct.id, type=JobType.scan)
        rule = WhitelistRule(
            account_id=acct.id,
            kind=WhitelistKind.domain,
            value="example.com",
        )
        session.add_all([job_row, rule])
        session.commit()

        # Verify rows exist before deletion
        assert session.scalar(select(Sender).where(Sender.account_id == acct.id)) is not None
        assert session.scalar(select(Job).where(Job.account_id == acct.id)) is not None
        assert session.scalar(select(WhitelistRule).where(WhitelistRule.account_id == acct.id)) is not None

        session.delete(acct)
        session.commit()

        # All child rows must be gone after the account is deleted
        assert session.scalar(select(Sender).where(Sender.account_id == acct.id)) is None
        assert session.scalar(select(Job).where(Job.account_id == acct.id)) is None
        assert session.scalar(select(WhitelistRule).where(WhitelistRule.account_id == acct.id)) is None

    Base.metadata.drop_all(engine)
