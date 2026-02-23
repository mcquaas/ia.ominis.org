'use client';

import { useSearchParams } from 'next/navigation';
import { LoginForm } from '@/components/auth';

export default function LoginPageClient() {
  const searchParams = useSearchParams();
  const next = searchParams.get('next');
  const redirectTo = next ? decodeURIComponent(next) : undefined;
  return <LoginForm redirectTo={redirectTo} />;
}
