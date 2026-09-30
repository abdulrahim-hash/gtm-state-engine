import { AccountDetailScreen } from "@/components/account-detail-screen";

type AccountDetailPageProps = {
  params: Promise<{ accountId: string }>;
};

export default async function AccountDetailPage({ params }: AccountDetailPageProps) {
  const { accountId } = await params;
  return <AccountDetailScreen accountId={accountId} />;
}
