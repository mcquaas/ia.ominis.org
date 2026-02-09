import Header from "@/components/Header";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[#0a1628] overflow-x-hidden max-w-[100vw]">
      <Header />
      {children}
    </main>
  );
}
