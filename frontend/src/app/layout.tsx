import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import Providers from "@/components/Providers";
import "./globals.css";

const GA_MEASUREMENT_ID = "G-4WG5KD81EQ";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://ai.ominis.org";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
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
    images: [
      {
        url: "/ominis-preview.png",
        width: 1200,
        height: 630,
        alt: "Ominis AI",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Ominis AI - Asistente para la Investigación en Salud",
    description: "Asistente de IA para investigadores en salud. Fuentes de datos y estudios sobre el sistema de salud en México.",
    images: ["/ominis-preview.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="overflow-x-hidden">
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
