import { FC, useEffect } from 'react';
import { AxiosError } from 'axios';
import { useIntl } from 'react-intl';
import { FormProvider, SubmitHandler, useForm } from 'react-hook-form';
import { Redirect } from 'react-router-dom';
import { useMutation } from 'react-query';
import { postEditMfaConfigConfirm } from 'api/auth';
import useUserSettingsMfaContext from 'context/UserSettingsMfaContext';
import routeList from 'routes/routeList';
import CustomButton from 'components/shared/CustomButton';
import FormInput from 'components/forms/FormInput';
import UserSettingsMfaConfigSuccess from 'components/pages/userSettingsMfaConfig/UserSettingsMfaConfigSuccess';
import UserSettingsMfaConfigError from 'components/pages/userSettingsMfaConfig/UserSettingsMfaConfigError';
import { vaildateMfaCode } from 'components/forms/validation/validationSchema';
import MfaQRCode from 'components/shared/MfaQRCode';

type TMfaConfigForm = {
  token: string;
  mfa_code: string;
};

const UserSettingsMfaConfigForm: FC = () => {
  const { messages } = useIntl();
  const { state, mfaData, updateUserSettingsMfaState } = useUserSettingsMfaContext();

  const methods = useForm<TMfaConfigForm>({ mode: 'onBlur', defaultValues: { mfa_code: '' } });
  const { setValue, setError, handleSubmit, setFocus } = methods;

  const { mutateAsync: confirmMfa, status: confirmMfaStatus } = useMutation<void, AxiosError, TMfaConfigForm>((data) =>
    postEditMfaConfigConfirm(data)
  );

  const onSubmit: SubmitHandler<TMfaConfigForm> = async (data) => {
    const formData = { ...data, token: mfaData?.token || '' };

    try {
      await confirmMfa(formData, {
        onSuccess: () => {
          updateUserSettingsMfaState('success');
        }
      });
    } catch (error) {
      const { status } = error.response || {};

      switch (status) {
        case 409:
          setValue('mfa_code', '');
          setError('mfa_code', { type: 'manual', message: 'validation_badMfaCode' });
          break;
        case 400:
        case 403:
        case 500:
        default:
          updateUserSettingsMfaState('error');
          break;
      }
    }
  };

  useEffect(() => {
    if (state === 'form') setFocus('mfa_code');
  }, [state, setFocus]);

  switch (state) {
    case 'form':
      return (
        <div className="user-settings-config-content mfa">
          <h1 className="mb-30 text-center">{messages.login_mfa_config_title}</h1>
          <div className="mfa-config-form-wrapper">
            <div className="mfa-config-step-wrapper mb-0">
              <p>{messages.login_mfa_config_step_1}</p>
              <p>{messages.login_mfa_config_step_2}</p>
            </div>
            {mfaData?.mfa_config && <MfaQRCode {...mfaData.mfa_config} />}
            <div className="mfa-config-step-wrapper">
              <p>{messages.login_mfa_config_step_3}</p>
            </div>
            <FormProvider {...methods}>
              <form className="mfa-config-form w-100" onSubmit={handleSubmit(onSubmit)}>
                <FormInput
                  name="mfa_code"
                  label={`${messages.login_mfa_config_input_label}`}
                  maxLength="8"
                  validate={vaildateMfaCode}
                />
                <div className="d-flex mt-4">
                  <CustomButton
                    to={routeList.userSettings}
                    className="w-100"
                    text={`${messages.login_mfa_config_btn_cancel}`}
                    variant="link"
                    disabled={confirmMfaStatus === 'loading'}
                  />
                  <CustomButton
                    type="submit"
                    className="w-100"
                    text={`${messages.login_mfa_config_btn_confirm}`}
                    variant="primary"
                    loading={confirmMfaStatus === 'loading'}
                    disabled={confirmMfaStatus === 'loading'}
                  />
                </div>
              </form>
            </FormProvider>
          </div>
        </div>
      );
    case 'success':
      return <UserSettingsMfaConfigSuccess />;
    case 'error':
      return <UserSettingsMfaConfigError />;
    default:
      return <Redirect to={routeList.userSettings} />;
  }
};

export default UserSettingsMfaConfigForm;
