import { FC, useState } from 'react';
import { Redirect } from 'react-router';
import { useIntl } from 'react-intl';
import useAuthContext from 'context/AuthContext';
import routeList from 'routes/routeList';
import { ReactComponent as Logo } from 'images/logo_n6.svg';
import SignUpStepOne from 'components/pages/signUp/SignUpStepOne';
import SignUpStepTwo from 'components/pages/signUp/SignUpStepTwo';
import LanguagePicker from 'components/shared/LanguagePicker';
import SignUpSuccess from 'components/pages/signUp/SignUpSuccess';
import SignUpWizard from 'components/pages/signUp/SignUpWizard';
import { signup_terms } from 'dictionary';

const SignUp: FC = () => {
  const { messages } = useIntl();
  const [formStep, setFormStep] = useState(1);
  const [tosVersions, changeTosVersions] = useState({ en: signup_terms.en.version, pl: signup_terms.pl.version });

  const { isAuthenticated } = useAuthContext();

  if (isAuthenticated) return <Redirect to={routeList.incidents} />;

  return (
    <div className="signup-wrapper font-bigger">
      <div className="signup-logo" aria-hidden="true">
        <Logo />
      </div>
      <SignUpWizard pageIdx={1} formStep={formStep}>
        <h1 className="signup-title mb-30 text-center">
          {messages.signup_title} <span>({formStep}/2)</span>
        </h1>
        <div className="signup-language text-center">
          <LanguagePicker mode="icon" buttonClassName="mx-2" />
        </div>
        <SignUpStepOne changeStep={setFormStep} changeTosVersions={changeTosVersions} />
      </SignUpWizard>
      <SignUpWizard pageIdx={2} formStep={formStep}>
        <h1 className="signup-title mb-5 text-center">
          {messages.signup_title} <span>({formStep}/2)</span>
        </h1>
        <SignUpStepTwo changeStep={setFormStep} tosVersions={tosVersions} />
      </SignUpWizard>
      <SignUpWizard pageIdx={3} formStep={formStep}>
        <SignUpSuccess />
      </SignUpWizard>
    </div>
  );
};

export default SignUp;
