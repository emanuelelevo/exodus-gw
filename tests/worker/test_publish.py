import uuid
from datetime import datetime, timezone

import mock

from exodus_gw import models, worker

NOW_UTC = datetime.now(timezone.utc)


def _task(publish_id):
    return models.Task(
        id="8d8a4692-c89b-4b57-840f-b3f0166148d2",
        publish_id=publish_id,
        state="NOT_STARTED",
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit(mock_write_batches, mock_get_message, fake_publish, db):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )
    # Simulate successful write of items by write_batches.
    mock_write_batches.return_value = True

    db.add(fake_publish)
    db.add(task)
    # Caller would've set publish state to COMMITTING.
    fake_publish.state = "COMMITTING"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It should've set task state to COMPLETE.
    db.refresh(task)
    assert task.state == "COMPLETE"
    # It should've set publish state to COMMITTED.
    db.refresh(fake_publish)
    assert fake_publish.state == "COMMITTED"

    # It should've called write_batches for items and entry point items.
    mock_write_batches.assert_has_calls(
        calls=[
            mock.call("test", mock.ANY, NOW_UTC),
            mock.call("test", mock.ANY, NOW_UTC),
        ]
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_write_items_fail(
    mock_write_batches, mock_get_message, fake_publish, db
):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )
    # Simulate failed write of items and successful deletion of items.
    mock_write_batches.side_effect = [False, True]

    db.add(fake_publish)
    db.add(task)
    # Caller would've set publish state to COMMITTING.
    fake_publish.state = "COMMITTING"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It should've set task state to FAILED.
    db.refresh(task)
    assert task.state == "FAILED"
    # It should've set publish state to FAILED.
    db.refresh(fake_publish)
    assert fake_publish.state == "FAILED"

    # It should've called write_batches for items and deletion of items.
    mock_write_batches.assert_has_calls(
        calls=[
            mock.call("test", mock.ANY, NOW_UTC),
            mock.call("test", mock.ANY, NOW_UTC, delete=True),
        ],
        any_order=False,
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_write_entry_point_items_fail(
    mock_write_batches, mock_get_message, fake_publish, db
):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )
    # Simulate successful write of items, failed write of entry point items
    # and then successful deletion of items.
    mock_write_batches.side_effect = [True, False, True]

    db.add(fake_publish)
    db.add(task)
    # Caller would've set publish state to COMMITTING.
    fake_publish.state = "COMMITTING"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It should've set task state to FAILED.
    db.refresh(task)
    assert task.state == "FAILED"
    # It should've set publish state to FAILED.
    db.refresh(fake_publish)
    assert fake_publish.state == "FAILED"

    # It should've called write_batches for items, entry point items
    # and then deletion of all items.
    mock_write_batches.assert_has_calls(
        calls=[
            mock.call("test", mock.ANY, NOW_UTC),
            mock.call("test", mock.ANY, NOW_UTC),
            mock.call("test", mock.ANY, NOW_UTC, delete=True),
        ],
        any_order=False,
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_write_exception(
    mock_write_batches, mock_get_message, fake_publish, db, caplog
):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )
    # Simulate failed write and deletion of items.
    mock_write_batches.side_effect = [False, RuntimeError()]

    db.add(fake_publish)
    db.add(task)
    # Caller would've set publish state to COMMITTING.
    fake_publish.state = "COMMITTING"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It should've set task state to FAILED.
    db.refresh(task)
    assert task.state == "FAILED"
    # It should've set publish state to FAILED.
    db.refresh(fake_publish)
    assert fake_publish.state == "FAILED"

    assert (
        "Task 8d8a4692-c89b-4b57-840f-b3f0166148d2 encountered an error"
        in caplog.text
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_completed_task(
    mock_write_batches, mock_get_message, db, caplog
):
    # Construct task that would be generated by caller.
    task = _task(publish_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174000"))
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": task.publish_id}
    )

    db.add(task)
    # Simulate prior completion of task.
    task.state = "COMPLETE"
    db.commit()

    worker.commit(str(task.publish_id), "test", NOW_UTC)

    # It shouldn't have called write_batches.
    mock_write_batches.assert_not_called()

    # It should've logged a warning message.
    assert (
        "Task 8d8a4692-c89b-4b57-840f-b3f0166148d2 in unexpected state, 'COMPLETE'"
        in caplog.text
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_completed_publish(
    mock_write_batches, mock_get_message, fake_publish, db, caplog
):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )

    db.add(task)
    db.add(fake_publish)
    # Simulate prior completion of publish.
    fake_publish.state = "COMPLETE"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It shouldn't have called write_batches.
    mock_write_batches.assert_not_called()

    # It should've logged a warning message.
    assert (
        "Publish %s in unexpected state, 'COMPLETE'" % fake_publish.id
        in caplog.text
    )


@mock.patch("exodus_gw.worker.publish.CurrentMessage.get_current_message")
@mock.patch("exodus_gw.worker.publish.write_batches")
def test_commit_empty_publish(
    mock_write_batches, mock_get_message, fake_publish, db
):
    # Construct task that would be generated by caller.
    task = _task(fake_publish.id)
    # Construct dramatiq message that would be generated by caller.
    mock_get_message.return_value = mock.MagicMock(
        message_id=task.id, kwargs={"publish_id": fake_publish.id}
    )

    # Empty the publish.
    fake_publish.items = []

    db.add(fake_publish)
    db.add(task)
    # Caller would've set publish state to COMMITTING.
    fake_publish.state = "COMMITTING"
    db.commit()

    worker.commit(str(fake_publish.id), fake_publish.env, NOW_UTC)

    # It should've set task state to COMPLETE.
    db.refresh(task)
    assert task.state == "COMPLETE"
    # It should've set publish state to COMMITTED.
    db.refresh(fake_publish)
    assert fake_publish.state == "COMMITTED"

    # It should not have called write_batches.
    mock_write_batches.assert_not_called()
