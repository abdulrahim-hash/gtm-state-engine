import { ImportBatchScreen } from "@/components/import-batch-screen";

type Props = {
  params: Promise<{ workspaceId: string; batchId: string }>;
};

export default async function ImportBatchPage({ params }: Props) {
  const { workspaceId, batchId } = await params;
  return <ImportBatchScreen workspaceId={workspaceId} batchId={batchId} />;
}
