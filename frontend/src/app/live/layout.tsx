import Image from "next/image";
import Link from "next/link";

export default function LiveLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[#0a1628] overflow-x-hidden max-w-[100vw]">
      <header className="fixed top-0 left-0 right-0 z-[9999] bg-[#0a1628]/90 backdrop-blur-sm border-b border-white/10 pt-[env(safe-area-inset-top)]">
        <nav className="px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/c" className="flex items-center gap-3">
              <Image
                src="/logo.png"
                alt="OMINIS"
                width={120}
                height={36}
                className="h-7 w-auto"
                priority
              />
              <span className="hidden sm:inline text-gray-400 text-xs border-l border-white/20 pl-3">
                Chat
              </span>
            </Link>
            <div className="flex items-center gap-4">
              <span className="text-cyan-400 text-sm font-medium">Live Avatar</span>
              <Link
                href="/c"
                className="text-gray-400 hover:text-cyan-300 transition-colors text-sm flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Ir al chat
              </Link>
            </div>
          </div>
        </nav>
      </header>
      <div className="pt-20 pb-8 px-4 sm:px-6 lg:px-8">
        {children}
      </div>
    </main>
  );
}
