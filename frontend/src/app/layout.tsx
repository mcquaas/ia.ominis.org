import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import Providers from "@/components/Providers";
import "./globals.css";

const GA_MEASUREMENT_ID = "G-4WG5KD81EQ";

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
      <head>
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="google-analytics" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${GA_MEASUREMENT_ID}');
          `}
        </Script>
      </head>
      <body className={`${inter.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
