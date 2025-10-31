import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, CallbackQuery
from telegram.ext import ContextTypes
from handlers.course_handlers import register_course_callback, register_certificate_choice_callback
from database import crud
from database.models import Course, User as DBUser, Enrollment, PaymentStatus

@pytest.fixture
def mock_db_session():
    """Mock a SQLAlchemy session."""
    session = MagicMock()
    yield session
    session.close()

@pytest.fixture
def mock_context():
    """Mock the context object."""
    context = AsyncMock()
    context.user_data = {}
    return context

@pytest.fixture
def mock_update(telegram_user_id=12345):
    """Mock the update object with a callback query."""
    update = AsyncMock(spec=Update)
    update.callback_query = AsyncMock(spec=CallbackQuery)
    update.callback_query.from_user = MagicMock(spec=User, id=telegram_user_id, username="testuser", first_name="Test", last_name="User")
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update

@pytest.mark.asyncio
async def test_register_course_no_certificate_direct_to_payment(mock_update, mock_context, mock_db_session):
    """
    Test direct registration for a course without a certificate.
    Should create enrollment and proceed to payment.
    """
    course_id = 1
    course_price = 100.0
    mock_update.callback_query.data = f"register_course_{course_id}"

    # Mock database interactions
    mock_course = MagicMock(spec=Course, course_id=course_id, course_name="Test Course", price=course_price, certificate_available=False, certificate_price=0)
    mock_db_user = MagicMock(spec=DBUser, user_id=1, telegram_user_id=mock_update.callback_query.from_user.id)
    mock_enrollment = MagicMock(spec=Enrollment, enrollment_id=101, user_id=mock_db_user.user_id, course_id=course_id, payment_amount=course_price, with_certificate=False)

    with MagicMock(return_value=mock_db_session) as get_db_mock:
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_course
        crud.get_or_create_user.return_value = mock_db_user
        crud.is_user_enrolled.return_value = False
        crud.create_enrollment.return_value = mock_enrollment

        # Mock the proceed_to_payment_callback from payment_handlers
        with pytest.MonkeyPatch().context() as m:
            m.setattr("handlers.payment_handlers.proceed_to_payment_callback", AsyncMock())
            from handlers.payment_handlers import proceed_to_payment_callback

            await register_course_callback(mock_update, mock_context)

            mock_update.callback_query.answer.assert_awaited_once()
            crud.get_or_create_user.assert_called_once()
            crud.get_course_by_id.assert_called_once_with(mock_db_session, course_id)
            crud.is_user_enrolled.assert_called_once_with(mock_db_session, mock_db_user.user_id, course_id)
            crud.create_enrollment.assert_called_once_with(mock_db_session, mock_db_user.user_id, course_id, course_price)
            mock_db_session.commit.assert_called_once()

            assert mock_context.user_data['cart_total_for_payment'] == course_price
            assert mock_context.user_data['pending_enrollment_ids_for_payment'] == [mock_enrollment.enrollment_id]
            assert mock_context.user_data['awaiting_receipt_upload'] is True
            assert mock_context.user_data['expected_amount_for_gemini'] == course_price

            proceed_to_payment_callback.assert_awaited_once_with(mock_update, mock_context)
            mock_update.callback_query.edit_message_text.assert_not_awaited() # Should not edit message, proceed to payment

@pytest.mark.asyncio
async def test_register_course_with_certificate_option_displayed(mock_update, mock_context, mock_db_session):
    """
    Test registration for a course with a certificate available.
    Should display certificate options.
    """
    course_id = 2
    course_price = 150.0
    certificate_price = 50.0
    mock_update.callback_query.data = f"register_course_{course_id}"

    mock_course = MagicMock(spec=Course, course_id=course_id, course_name="Cert Course", price=course_price, certificate_available=True, certificate_price=certificate_price)
    mock_db_user = MagicMock(spec=DBUser, user_id=1, telegram_user_id=mock_update.callback_query.from_user.id)

    with MagicMock(return_value=mock_db_session) as get_db_mock:
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_course
        crud.get_or_create_user.return_value = mock_db_user
        crud.is_user_enrolled.return_value = False

        await register_course_callback(mock_update, mock_context)

        mock_update.callback_query.answer.assert_awaited_once()
        crud.get_or_create_user.assert_called_once()
        crud.get_course_by_id.assert_called_once_with(mock_db_session, course_id)
        crud.is_user_enrolled.assert_called_once_with(mock_db_session, mock_db_user.user_id, course_id)
        mock_db_session.commit.assert_not_called() # No enrollment yet

        mock_update.callback_query.edit_message_text.assert_awaited_once()
        args, kwargs = mock_update.callback_query.edit_message_text.call_args
        assert "هل تريد التسجيل مع شهادة؟" in args[0]
        assert "reply_markup" in kwargs
        assert "register_cert_yes_2" in str(kwargs['reply_markup']) # Check for new callback data

@pytest.mark.asyncio
async def test_register_certificate_choice_yes_direct_to_payment(mock_update, mock_context, mock_db_session):
    """
    Test choosing 'yes' for certificate during direct registration.
    Should create enrollment with certificate and proceed to payment.
    """
    course_id = 3
    course_price = 200.0
    certificate_price = 75.0
    expected_total = course_price + certificate_price
    mock_update.callback_query.data = f"register_cert_yes_{course_id}"

    mock_course = MagicMock(spec=Course, course_id=course_id, course_name="Advanced Course", price=course_price, certificate_available=True, certificate_price=certificate_price)
    mock_db_user = MagicMock(spec=DBUser, user_id=1, telegram_user_id=mock_update.callback_query.from_user.id)
    mock_enrollment = MagicMock(spec=Enrollment, enrollment_id=102, user_id=mock_db_user.user_id, course_id=course_id, payment_amount=expected_total, with_certificate=True)

    with MagicMock(return_value=mock_db_session) as get_db_mock:
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_course
        crud.get_or_create_user.return_value = mock_db_user
        crud.create_enrollment.return_value = mock_enrollment

        with pytest.MonkeyPatch().context() as m:
            m.setattr("handlers.payment_handlers.proceed_to_payment_callback", AsyncMock())
            from handlers.payment_handlers import proceed_to_payment_callback

            await register_certificate_choice_callback(mock_update, mock_context)

            mock_update.callback_query.answer.assert_awaited_once()
            crud.get_or_create_user.assert_called_once()
            crud.get_course_by_id.assert_called_once_with(mock_db_session, course_id)
            crud.create_enrollment.assert_called_once_with(mock_db_session, mock_db_user.user_id, course_id, expected_total)
            mock_db_session.commit.assert_called_once()
            assert mock_enrollment.with_certificate is True

            assert mock_context.user_data['cart_total_for_payment'] == expected_total
            assert mock_context.user_data['pending_enrollment_ids_for_payment'] == [mock_enrollment.enrollment_id]
            assert mock_context.user_data['awaiting_receipt_upload'] is True
            assert mock_context.user_data['expected_amount_for_gemini'] == expected_total

            proceed_to_payment_callback.assert_awaited_once_with(mock_update, mock_context)
            mock_update.callback_query.edit_message_text.assert_not_awaited()

@pytest.mark.asyncio
async def test_register_certificate_choice_no_direct_to_payment(mock_update, mock_context, mock_db_session):
    """
    Test choosing 'no' for certificate during direct registration.
    Should create enrollment without certificate and proceed to payment.
    """
    course_id = 4
    course_price = 120.0
    certificate_price = 40.0
    expected_total = course_price # No certificate
    mock_update.callback_query.data = f"register_cert_no_{course_id}"

    mock_course = MagicMock(spec=Course, course_id=course_id, course_name="Basic Course", price=course_price, certificate_available=True, certificate_price=certificate_price)
    mock_db_user = MagicMock(spec=DBUser, user_id=1, telegram_user_id=mock_update.callback_query.from_user.id)
    mock_enrollment = MagicMock(spec=Enrollment, enrollment_id=103, user_id=mock_db_user.user_id, course_id=course_id, payment_amount=expected_total, with_certificate=False)

    with MagicMock(return_value=mock_db_session) as get_db_mock:
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_course
        crud.get_or_create_user.return_value = mock_db_user
        crud.create_enrollment.return_value = mock_enrollment

        with pytest.MonkeyPatch().context() as m:
            m.setattr("handlers.payment_handlers.proceed_to_payment_callback", AsyncMock())
            from handlers.payment_handlers import proceed_to_payment_callback

            await register_certificate_choice_callback(mock_update, mock_context)

            mock_update.callback_query.answer.assert_awaited_once()
            crud.get_or_create_user.assert_called_once()
            crud.get_course_by_id.assert_called_once_with(mock_db_session, course_id)
            crud.create_enrollment.assert_called_once_with(mock_db_session, mock_db_user.user_id, course_id, expected_total)
            mock_db_session.commit.assert_called_once()
            assert mock_enrollment.with_certificate is False

            assert mock_context.user_data['cart_total_for_payment'] == expected_total
            assert mock_context.user_data['pending_enrollment_ids_for_payment'] == [mock_enrollment.enrollment_id]
            assert mock_context.user_data['awaiting_receipt_upload'] is True
            assert mock_context.user_data['expected_amount_for_gemini'] == expected_total

            proceed_to_payment_callback.assert_awaited_once_with(mock_update, mock_context)
            mock_update.callback_query.edit_message_text.assert_not_awaited()
