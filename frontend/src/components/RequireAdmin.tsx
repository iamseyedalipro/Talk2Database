import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';

/** Route guard: only `admin` users may pass; others are sent to the home page. */
export default function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (!user || user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
