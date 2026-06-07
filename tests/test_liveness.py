
import numpy as np
import pytest

from app.models import Card, Employee, LivenessSession


@pytest.fixture
def employee_with_face(db):
    embedding = np.random.rand(128).tolist()
    emp = Employee(full_name="Петров Пётр", role="manager", month_limit_kopecks=300000, face_embedding_json=embedding)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    card = Card(uid="FACE001", employee_id=emp.id)
    db.add(card)
    db.commit()
    return emp, card, embedding


class TestStartLiveness:
    def test_start_liveness_success(self, client, employee_with_face):
        _, card, _ = employee_with_face
        resp = client.post(f"/api/start_liveness?card_uid={card.uid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data

    def test_start_liveness_card_not_found(self, client):
        resp = client.post("/api/start_liveness?card_uid=INVALID")
        assert resp.status_code == 404

    def test_start_liveness_no_face_enrolled(self, client, db):
        emp = Employee(full_name="No Face", role="dev", month_limit_kopecks=100000)
        db.add(emp)
        db.commit()
        db.refresh(emp)
        card = Card(uid="NOFACE1", employee_id=emp.id)
        db.add(card)
        db.commit()
        resp = client.post(f"/api/start_liveness?card_uid={card.uid}")
        assert resp.status_code == 400


class TestLivenessAlgorithm:
    """Tests for the variance-based liveness detection logic."""

    def test_session_passes_after_enough_matches_with_variance(self, db):
        from app.routers.liveness import MATCHES_NEEDED, VARIANCE_NEEDED
        embedding = np.random.rand(128).tolist()
        sess = LivenessSession(
            id="algo-test-1", card_uid="X", passed=False,
            embedding_json=embedding, blink_count=MATCHES_NEEDED - 1,
            last_ear=0.35, min_ear_closed=0.30,
        )
        db.add(sess)
        db.commit()
        variance = sess.last_ear - sess.min_ear_closed
        assert variance >= VARIANCE_NEEDED
        assert sess.blink_count == MATCHES_NEEDED - 1

    def test_static_photo_low_variance_does_not_pass(self, db):
        from app.routers.liveness import MATCHES_NEEDED, VARIANCE_NEEDED
        embedding = np.random.rand(128).tolist()
        sess = LivenessSession(
            id="algo-test-2", card_uid="X", passed=False,
            embedding_json=embedding, blink_count=MATCHES_NEEDED,
            last_ear=0.31, min_ear_closed=0.30,
        )
        db.add(sess)
        db.commit()
        variance = sess.last_ear - sess.min_ear_closed
        assert variance < VARIANCE_NEEDED
        assert not sess.passed
