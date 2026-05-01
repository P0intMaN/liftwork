import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./providers/AuthProvider";
import { AppShell } from "./components/layout/AppShell";
import LoginPage from "./pages/Login";
import OverviewPage from "./pages/Overview";
import ApplicationsPage from "./pages/Applications";
import ApplicationDetailPage from "./pages/ApplicationDetail";
import BuildDetailPage from "./pages/BuildDetail";
import ClustersPage from "./pages/Clusters";
import ActivityPage from "./pages/Activity";

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="grid h-screen place-items-center text-sm text-muted-foreground">
        loading liftwork…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <Protected />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <OverviewPage /> },
          { path: "/applications", element: <ApplicationsPage /> },
          { path: "/applications/:id", element: <ApplicationDetailPage /> },
          { path: "/builds/:id", element: <BuildDetailPage /> },
          { path: "/clusters", element: <ClustersPage /> },
          { path: "/activity", element: <ActivityPage /> },
        ],
      },
    ],
  },
]);
