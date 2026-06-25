import { Link } from "@/i18n/navigation";
import { getTranslations } from "next-intl/server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "nav" });
  return {
    title: `${t("terms")} — PokéDeals`,
    description: "Terms of use and disclaimer for PokéDeals.",
  };
}

export default async function TermsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const tNav = await getTranslations({ locale, namespace: "nav" });

  return (
    <main className="min-h-screen bg-[#f1f0ec] text-gray-900 font-sans p-6 md:p-10">
      <div className="max-w-2xl mx-auto space-y-6 text-sm leading-relaxed">
        <Link href="/" className="text-[#4b3585] font-bold text-sm hover:underline">
          ← {tNav("home")}
        </Link>
        <h1 className="text-2xl font-extrabold">{tNav("terms")} & disclaimer</h1>
        <p className="text-gray-600">
          PokéDeals aggregates publicly visible product information (such as titles, prices, and links) from
          third-party shops to help you compare offers. It does not sell products and is not affiliated with
          The Pokémon Company, Nintendo, or the listed retailers unless stated otherwise.
        </p>
        <h2 className="text-lg font-bold pt-2">Accuracy</h2>
        <p className="text-gray-600">
          Prices, availability, and product details can change at any time on the merchant&apos;s website.
          Always confirm the final price, shipping, and stock on the shop before you purchase. We do not
          guarantee that data is complete, current, or error-free.
        </p>
        <h2 className="text-lg font-bold pt-2">Links</h2>
        <p className="text-gray-600">
          Outbound links leave this site. You are subject to each shop&apos;s own terms, privacy policy, and
          checkout process.
        </p>
        <h2 className="text-lg font-bold pt-2">Use of the service</h2>
        <p className="text-gray-600">
          You agree to use this site for lawful purposes only. Automated scraping of PokéDeals itself (as
          opposed to the official scraper you run for your own deployment) may be blocked.
        </p>
        <p className="text-xs text-gray-500 pt-4">
          This text is informational and not legal advice. Have a qualified professional review it for your
          jurisdiction before a public launch.
        </p>
      </div>
    </main>
  );
}
