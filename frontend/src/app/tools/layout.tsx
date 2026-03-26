import Header from "@/components/Header";

export default function ToolsLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-[#0a1628] overflow-x-hidden max-w-[100vw]">
      <Header />
      <div className="pt-[calc(4rem+var(--banner-height,0px)+env(safe-area-inset-top))] px-4 sm:px-6 pb-12">
        {children}
      </div>
    </main>
  );
}
