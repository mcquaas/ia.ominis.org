import Link from "next/link";

export default function ToolsIndexPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold text-white mb-2">Herramientas</h1>
      <p className="text-sm text-gray-400 mb-6">
        Búsquedas y directorios disponibles también desde el menú del chat (icono +). Inicia sesión para directorios que requieren cuenta.
      </p>
      <ul className="space-y-3">
        <li>
          <Link href="/tools/clinical-trials" className="block rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-white hover:border-teal-500/40 transition-colors">
            <span className="font-medium">ClinicalTrials.gov (México)</span>
            <span className="block text-xs text-gray-400 mt-1">Consulta asistida sobre ensayos clínicos registrados (ubicación México).</span>
          </Link>
        </li>
        <li>
          <Link href="/tools/directorio-mx" className="block rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-white hover:border-emerald-500/40 transition-colors">
            <span className="font-medium">Directorio MX</span>
            <span className="block text-xs text-gray-400 mt-1">Médicos ingeridos desde fuentes públicas (Top Doctors, Doctoralia, DoctorAnytime).</span>
          </Link>
        </li>
        <li>
          <Link href="/tools/allcan" className="block rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-white hover:border-orange-500/40 transition-colors">
            <span className="font-medium">All.Can México</span>
            <span className="block text-xs text-gray-400 mt-1">Organizaciones del mapa interactivo All.Can (Strapi).</span>
          </Link>
        </li>
        <li>
          <Link href="/c" className="block rounded-xl border border-white/10 px-4 py-3 text-cyan-300 hover:bg-white/5 transition-colors text-sm">
            Volver al chat
          </Link>
        </li>
      </ul>
    </div>
  );
}
