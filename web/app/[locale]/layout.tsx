import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Link } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { getTranslations } from "next-intl/server";
import { getSiteUrl } from "@/lib/site";
import "../globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const metadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  applicationName: "PokéDeals",
  creator: "PokéDeals",
  publisher: "PokéDeals",
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
};

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as "en" | "hu")) {
    notFound();
  }

  setRequestLocale(locale);
  const messages = await getMessages();
  const t = await getTranslations({ locale, namespace: "footer" });
  const tNav = await getTranslations({ locale, namespace: "nav" });

  return (
    <html
      lang={locale}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#f1f0ec]">
        <NextIntlClientProvider messages={messages}>
          <div className="flex-1 flex flex-col">{children}</div>
          <footer className="border-t border-gray-200 bg-white/80 py-6 text-center text-xs text-gray-500">
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
              <Link href="/terms" className="hover:text-gray-800 underline underline-offset-2">
                {tNav("terms")}
              </Link>
              <Link href="/privacy" className="hover:text-gray-800 underline underline-offset-2">
                {tNav("privacy")}
              </Link>
              <span className="hidden sm:inline text-gray-300">·</span>
              <span>{t("disclaimer")}</span>
            </div>
          </footer>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
