import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from './store/authStore';
import { useCurrencyStore } from './store/currencyStore';
import { useUnitStore } from './store/unitStore';
import { safeNext } from './utils/nextPath';
import Layout from './components/Layout';
import Login from './views/Login';
import Register from './views/Register';
import ResetPassword from './views/ResetPassword';
import JoinCar from './views/JoinCar';
import VerifyEmail from './views/VerifyEmail';
import Dashboard from './views/Dashboard';
import Logbook from './views/Logbook';
import LogDetail from './views/LogDetail';
import AddEntry from './views/AddEntry';
import Analytics from './views/Analytics';
import Diagnostics from './views/Diagnostics';
import Garage from './views/Garage';
import Intervals from './views/Intervals';
import Preferences from './views/Preferences';
import Profile from './views/Profile';
import CarEditor from './views/CarEditor';
import Tires from './views/Tires';
import YearReview from './views/YearReview';
import Documents from './views/Documents';
import Notifications from './views/Notifications';
import CarSpecs from './views/CarSpecs';
import CarPassport from './views/CarPassport';
import AdminUsers from './views/AdminUsers';
import AdminUserDetail from './views/AdminUserDetail';

function Protected({ children }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

// The admin section is gated on the loaded user's flag. While /auth/me is still
// in flight `user` is null, so we wait (a spinner-free null) rather than bounce
// a real superadmin to «/» on a slow first load.
function RequireSuperadmin({ children }) {
  const user = useAuthStore((s) => s.user);
  if (user === null) return null;
  if (!user.is_superadmin) return <Navigate to="/" replace />;
  return children;
}

function PublicOnly({ children }) {
  const token = useAuthStore((s) => s.token);
  const [searchParams] = useSearchParams();
  if (token) return <Navigate to={safeNext(searchParams.get('next'))} replace />;
  return children;
}

export default function App() {
  // Subscribe the root to the active language and currency. A change re-renders
  // the whole tree, so components that render domain-label helpers or money
  // (via format.js) without their own hook still refresh.
  useTranslation();
  useCurrencyStore((s) => s.currency);
  useUnitStore((s) => s.units);
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicOnly>
            <Login />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <Register />
          </PublicOnly>
        }
      />
      <Route
        path="/reset"
        element={
          <PublicOnly>
            <ResetPassword />
          </PublicOnly>
        }
      />
      <Route path="/join/:token" element={<JoinCar />} />
      <Route path="/verify" element={<VerifyEmail />} />
      <Route path="/p/:token" element={<CarPassport />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/logbook" element={<Logbook />} />
        <Route path="/logbook/:id" element={<LogDetail />} />
        <Route path="/add" element={<AddEntry />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/year" element={<YearReview />} />
        <Route path="/diagnostics" element={<Diagnostics />} />
        <Route path="/garage" element={<Garage />} />
        <Route path="/garage/new" element={<CarEditor />} />
        <Route path="/garage/:carId/edit" element={<CarEditor />} />
        <Route path="/intervals" element={<Intervals />} />
        <Route path="/preferences" element={<Preferences />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/tires" element={<Tires />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/garage/:carId/specs" element={<CarSpecs />} />
        <Route
          path="/admin"
          element={
            <RequireSuperadmin>
              <AdminUsers />
            </RequireSuperadmin>
          }
        />
        <Route
          path="/admin/users/:id"
          element={
            <RequireSuperadmin>
              <AdminUserDetail />
            </RequireSuperadmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
