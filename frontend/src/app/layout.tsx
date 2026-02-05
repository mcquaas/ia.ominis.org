import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ominis AI - Asistente para la Investigación en Salud",
  description: "Asistente de IA para investigadores en salud. Accede a fuentes de datos, estudios y documentación sobre el sistema de salud en México.",
  keywords: ["investigación en salud", "IA", "inteligencia artificial", "datos de salud", "México", "FUNSALUD", "OMINIS"],
  authors: [{ name: "Fundación Mexicana para la Salud A.C." }],
  openGraph: {
    title: "Ominis AI - Asistente para la Investigación en Salud",
    description: "Asistente de IA para investigadores en salud. Fuentes de datos y estudios sobre el sistema de salud en México.",
    url: "https://ai.ominis.org",
    siteName: "Ominis AI",
    locale: "es_MX",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className={`${inter.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
