'use client';

import { AuthProvider } from '@/hooks/useAuth';

export default function Providers({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
