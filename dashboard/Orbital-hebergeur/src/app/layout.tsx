import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Zilla_Slab } from "next/font/google";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n";
import { getLocale } from "@/lib/i18n-server";
import { ToastProvider } from "@/components/toast";
import { withPanelBase } from "@/lib/panel-base";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Zilla_Slab({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Synkrone",
  description: "Hébergement Synkrone — bots Discord, serveurs Minecraft et applications web.",
  icons: { icon: withPanelBase("/icon.svg") },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`${sans.variable} ${serif.variable} ${mono.variable}`}>
      <body className="min-h-screen antialiased">
        <I18nProvider initialLocale={locale}>
          <ToastProvider>{children}</ToastProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
