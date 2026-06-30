import { Link } from "@/i18n/navigation";
import { getTranslations } from "next-intl/server";
import { buildLegalMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return buildLegalMetadata(locale, "privacy");
}

export default async function PrivacyPage({
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
        <h1 className="text-2xl font-extrabold">{tNav("privacy")}</h1>
        <p className="text-gray-600">
          This dashboard loads aggregated listing data via the site&apos;s own API routes. We do not use
          marketing trackers or advertising cookies on this minimalist deployment by default — check your
          hosting provider&apos;s dashboard (for example Vercel analytics) if you enable analytics later.
        </p>
        <h2 className="text-lg font-bold pt-2">Outbound clicks</h2>
        <p className="text-gray-600">
          When you click a shop deal link, we may log an anonymous event (product, shop, price, destination
          URL, and basic request metadata) in your Supabase project to measure which offers are useful. No
          account is required and we do not sell this data.
        </p>
        <h2 className="text-lg font-bold pt-2">Data stored by you</h2>
        <p className="text-gray-600">
          Product records are stored in your Supabase project under your control. Review Supabase privacy and
          security settings for retention, backups, and access policies.
        </p>
        <h2 className="text-lg font-bold pt-2">Contact</h2>
        <p className="text-gray-600">
          Add a contact email or form here before inviting the general public — this stub is intentional.
        </p>
        <p className="text-xs text-gray-500 pt-4">
          This stub is informational, not legal advice. Align it with GDPR / local rules if you process
          personal data beyond basic server logs.
        </p>
      </div>
    </main>
  );
}
