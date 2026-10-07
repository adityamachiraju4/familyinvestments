import { RecordedContributions } from "../components/RecordedContributions";
import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Plan, Allocation } from "../components/Plan";
import { Card, State } from "../components/UI";
export default function Investments({ revision }: { revision: number }) {
  const target = useQuery(api.target, revision);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CONSISTENCY BUILDS WEALTH</p>
          <h1>Investments</h1>
          <p className="muted">Your household investment plan.</p>
        </div>
      </div>
      {target.loading || target.error ? (
        <State loading={target.loading} error={target.error} />
      ) : target.data ? (
        <div className="two-column">
          <Plan target={target.data} />
          <Allocation target={target.data} />
        </div>
      ) : (
        <State empty="No monthly target available." />
      )}
      <RecordedContributions revision={revision} />
      <Card title="A plan for the long term">
        <p className="muted">
          Your plan sits alongside recorded Zerodha delivery purchases. Complete
          monthly coverage will build as trade history is recorded.
        </p>
      </Card>
    </>
  );
}
