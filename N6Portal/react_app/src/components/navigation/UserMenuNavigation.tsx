import { FC, useState } from 'react';
import Dropdown from 'react-bootstrap/esm/Dropdown';
import { DropdownItemProps } from 'react-bootstrap/esm/DropdownItem';
import { useIntl } from 'react-intl';
import { useMutation } from 'react-query';
import { Link, useHistory } from 'react-router-dom';
import routeList from 'routes/routeList';
import { getLogout } from 'api/auth';
import useAuthContext from 'context/AuthContext';
import LanguagePicker from 'components/shared/LanguagePicker';

import { ReactComponent as User } from 'images/user.svg';

const UserMenuNavigation: FC = () => {
  const { resetAuthState } = useAuthContext();
  const { messages } = useIntl();
  const history = useHistory();
  const logoutFn = useMutation(getLogout);
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    throw new Error(`${messages.header_nav_logout_error}`);
  }

  const handleLogout = async () => {
    try {
      await logoutFn.mutateAsync();
      resetAuthState();
      history.push(routeList.login);
    } catch (error) {
      setHasError(true);
    }
  };

  const onLogoutClick = (e: React.MouseEvent<DropdownItemProps>): void => {
    e.preventDefault();
    handleLogout();
  };

  return (
    <Dropdown>
      <Dropdown.Toggle
        id="dropdown-user-menu"
        aria-label={`${messages.header_user_menu_aria_label}`}
        bsPrefix="header-user-btn"
        className="light-focus"
      >
        <User />
      </Dropdown.Toggle>
      <Dropdown.Menu align="right" className="header-dropdown-menu p-0">
        <Dropdown.Item as={Link} to={routeList.account} className="p-3">
          {messages.header_nav_account}
        </Dropdown.Item>
        <Dropdown.Divider className="m-0" />
        <Dropdown.Item as={Link} to={routeList.userSettings} className="p-3">
          {messages.header_nav_user_settings}
        </Dropdown.Item>
        <Dropdown.Item as={Link} to={routeList.settings} className="p-3">
          {messages.header_nav_settings}
        </Dropdown.Item>
        <Dropdown.Divider className="m-0" />
        <Dropdown.Item className="p-3">
          <LanguagePicker mode="text" />
        </Dropdown.Item>
        <Dropdown.Divider className="m-0" />
        <Dropdown.Item as={Link} to={routeList.login} className="p-3" onClick={onLogoutClick}>
          {messages.header_nav_logout}
        </Dropdown.Item>
      </Dropdown.Menu>
    </Dropdown>
  );
};

export default UserMenuNavigation;
