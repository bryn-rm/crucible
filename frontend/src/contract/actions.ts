/**
 * Environment action schemas.
 *
 * TypeScript mirror of backend/app/contract/actions.py.
 */

// --- Negotiation ---

export interface OfferAction {
  type: 'offer';
  split: Record<string, number>;
}

export interface AcceptAction {
  type: 'accept';
}

export interface WalkAction {
  type: 'walk';
}

export type NegotiationAction = OfferAction | AcceptAction | WalkAction;

// --- Role-play ---

export interface SayAction {
  type: 'say';
  text: string;
}

export interface EndInterviewAction {
  type: 'end_interview';
}

export type RolePlayAction = SayAction | EndInterviewAction;
