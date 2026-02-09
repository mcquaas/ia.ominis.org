import MainLayout from "@/components/MainLayout";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ uuid: string }>;
}) {
  const { uuid } = await params;
  return <MainLayout initialUuid={uuid} />;
}
