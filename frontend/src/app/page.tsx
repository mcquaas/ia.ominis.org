import Header from "@/components/Header";
import MainLayout from "@/components/MainLayout";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#0a1628]">
      <Header />
      <MainLayout />
      <Footer />
    </main>
  );
}
