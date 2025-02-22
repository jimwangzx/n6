import { FC } from 'react';
import { Redirect, Route } from 'react-router-dom';
import useAuthContext, { PermissionsStatus } from 'context/AuthContext';
import Loader from 'components/loading/Loader';

interface IPrivateRouteProps {
  path: string;
  exact: boolean;
  redirectPath: string;
}

const PrivateRoute: FC<IPrivateRouteProps> = ({ children, redirectPath, ...rest }) => {
  const { isAuthenticated, contextStatus } = useAuthContext();

  if (contextStatus === PermissionsStatus.initial) {
    return <Route {...rest} render={() => <Loader />} />;
  }

  return <Route {...rest} render={() => (isAuthenticated ? children : <Redirect to={redirectPath} />)} />;
};

export default PrivateRoute;
