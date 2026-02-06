import Image from "next/image";
import Link from "next/link";

export default function Footer() {
  return (
    <footer className="bg-[#0a1628] border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand */}
          <div>
            <Image
              src="/logo.png"
              alt="OMINIS"
              width={120}
              height={35}
              className="h-8 w-auto mb-4"
            />
            <p className="text-gray-500 text-sm">
              Observatorio Mexicano para la Investigación y la Inteligencia en Salud.
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-white font-semibold text-sm mb-3">Recursos</h3>
            <ul className="space-y-2">
              <li>
                <Link 
                  href="https://ominis.org" 
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-sm"
                >
                  Observatorio
                </Link>
              </li>
              <li>
                <Link 
                  href="https://roclab.ominis.org" 
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-sm"
                >
                  ROCLab
                </Link>
              </li>
            </ul>
          </div>

          {/* Organization */}
          <div>
            <h3 className="text-white font-semibold text-sm mb-3">Organización</h3>
            <ul className="space-y-2">
              <li>
                <Link 
                  href="https://funsalud.org.mx" 
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-sm"
                >
                  FUNSALUD
                </Link>
              </li>
              <li>
                <a 
                  href="mailto:ominis@funsalud.org.mx"
                  className="text-gray-400 hover:text-white transition-colors text-sm"
                >
                  Contacto
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom */}
        <div className="border-t border-white/10 mt-8 pt-6">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-gray-500 text-xs text-center md:text-left">
              © {new Date().getFullYear()} Fundación Mexicana para la Salud A.C. Todos los derechos reservados.
            </p>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full"></span>
              <span className="text-gray-500 text-xs">100% Datos en México</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
