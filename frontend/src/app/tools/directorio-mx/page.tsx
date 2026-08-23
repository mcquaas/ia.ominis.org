import DoctorDirectorySearch from "@/components/DoctorDirectorySearch";

export default function DirectorioMxToolPage() {
  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-lg font-semibold text-white mb-4">Directorio de médicos (México)</h1>
      <DoctorDirectorySearch layout="inline" />
    </div>
  );
}
