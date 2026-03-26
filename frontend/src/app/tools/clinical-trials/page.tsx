import ClinicalTrialsAssistClient from "./ClinicalTrialsAssistClient";

export default function ClinicalTrialsToolPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-lg font-semibold text-white mb-4">ClinicalTrials.gov — México</h1>
      <ClinicalTrialsAssistClient />
    </div>
  );
}
