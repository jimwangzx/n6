import { FC, useEffect } from 'react';
import { useIntl } from 'react-intl';
import { useHistory } from 'react-router-dom';
import { ReactComponent as SuccessIcon } from 'images/check-ico.svg';
import CustomButton from 'components/shared/CustomButton';
import routeList from 'routes/routeList';
import useForgotPasswordContext from 'context/ForgotPasswordContext';

const ResetPasswordSuccess: FC = () => {
  const { messages } = useIntl();
  const { resetForgotPasswordState } = useForgotPasswordContext();
  const history = useHistory();

  useEffect(() => {
    history.replace({ search: '' });
    return () => resetForgotPasswordState();
  }, [history, resetForgotPasswordState]);

  return (
    <section className="reset-password-container">
      <div className="reset-password-content">
        <div className="reset-password-icon">
          <SuccessIcon />
        </div>
        <div className="mb-30 reset-password-summary">
          <h1>{messages.reset_password_success_title}</h1>
          <p>{messages.reset_password_success_description}</p>
          <CustomButton to={routeList.login} text={`${messages.reset_password_success_btn}`} variant="primary" />
        </div>
      </div>
    </section>
  );
};

export default ResetPasswordSuccess;
