import { useState } from 'react';
import { MatchView } from './match/MatchView';
import { ReplayView } from './replay/ReplayView';
import { LeaderboardView } from './leaderboard/LeaderboardView';

type Tab = 'match' | 'replay' | 'leaderboard';

const TABS: { id: Tab; label: string }[] = [
  { id: 'match', label: 'Match' },
  { id: 'replay', label: 'Replay' },
  { id: 'leaderboard', label: 'Leaderboard' },
];

function App() {
  const [tab, setTab] = useState<Tab>('match');

  return (
    <div className="mx-auto min-h-screen max-w-5xl bg-neutral-950 px-6 py-8 text-neutral-100">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-medium">Multi-Agent Arena</h1>
        <nav className="flex gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === t.id
                  ? 'bg-neutral-100 text-neutral-950'
                  : 'text-neutral-400 hover:text-neutral-100'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === 'match' && <MatchView />}
      {tab === 'replay' && <ReplayView />}
      {tab === 'leaderboard' && <LeaderboardView />}
    </div>
  );
}

export default App;
