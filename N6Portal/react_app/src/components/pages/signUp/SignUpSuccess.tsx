import { FC } from 'react';
import { useHistory } from 'react-router-dom';
import { useIntl } from 'react-intl';
import routeList from 'routes/routeList';
import CustomButton from 'components/shared/CustomButton';
import { ReactComponent as SuccessIcon } from 'images/check-ico.svg';

const SignupSuccess: FC = () => {
  const { messages } = useIntl();
  const history = useHistory();
  return (
    <div className="d-flex flex-column align-items-center pt-lg-5">
      <SuccessIcon className="signup-success-icon" />
      <h1 className="signup-success-title mt-lg-5 mb-30 text-center">{messages.signup_success_header}</h1>
      <CustomButton
        className="mx-auto mb-60"
        text={`${messages.signup_success_btn}`}
        variant="primary"
        onClick={() => history.push(routeList.login)}
      />
    </div>
  );
};

export default SignupSuccess;
