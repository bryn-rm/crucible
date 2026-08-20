import { useState } from 'react';
import { MatchView } from './match/MatchView';
import { ReplayView } from './replay/ReplayView';
import { LeaderboardView } from './leaderboard/LeaderboardView';
import { TournamentView } from './tournament/TournamentView';

type Tab = 'match' | 'tournament' | 'replay' | 'leaderboard';

const TABS: { id: Tab; label: string }[] = [
  { id: 'match', label: 'Match' },
  { id: 'tournament', label: 'Tournament' },
  { id: 'replay', label: 'Replay' },
  { id: 'leaderboard', label: 'Leaderboard' },
];

function App() {
  const [tab, setTab] = useState<Tab>('match');

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-6 py-8 text-neutral-100">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-medium tracking-tight">CRUCIBLE <span className="text-xs text-emerald-300">/ ARENA</span></h1>
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
      {tab === 'tournament' && <TournamentView />}
      {tab === 'replay' && <ReplayView />}
      {tab === 'leaderboard' && <LeaderboardView />}
    </div>
  );
}

export default App;
