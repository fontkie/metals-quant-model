#!/usr/bin/env python3
"""Create 9-state regime classification"""

import pandas as pd
import sys

def main():
    print("="*80)
    print("CREATING 9-STATE REGIME CLASSIFICATION")
    print("="*80)
    
    # Load files
    print("\n1. Loading regime files...")
    crisis = pd.read_csv(sys.argv[1])
    crisis['date'] = pd.to_datetime(crisis['date'])
    crisis = crisis[['date', 'regime']].rename(columns={'regime': 'crisis_regime'})
    print(f"   ✓ Crisis: {len(crisis)} days")
    
    chop = pd.read_csv(sys.argv[2])
    chop['date'] = pd.to_datetime(chop['date'])
    chop = chop[['date', 'regime']].rename(columns={'regime': 'chop_regime'})
    print(f"   ✓ Chop: {len(chop)} days")
    
    vol = pd.read_csv(sys.argv[3])
    vol['date'] = pd.to_datetime(vol['date'])
    print(f"   ✓ Vol: {len(vol)} days")
    
    # Merge
    print("\n2. Merging regimes...")
    df = crisis.merge(chop, on='date', how='outer')
    df = df.merge(vol, on='date', how='outer')
    df = df.sort_values('date')
    print(f"   ✓ Total dates: {len(df)}")
    
    # Derive macro state
    print("\n3. Deriving macro state...")
    def get_macro(crisis, chop):
        if pd.isna(crisis):
            crisis = 'NORMAL'
        if pd.isna(chop):
            chop = 'NORMAL'
        if crisis in ['CRISIS', 'PRE_CRISIS']:
            return 'CRISIS'
        if chop in ['MILD_CHOP', 'HIGH_CHOP']:
            return 'CHOP'
        return 'NORMAL'
    
    df['macro_state'] = df.apply(lambda r: get_macro(r['crisis_regime'], r['chop_regime']), axis=1)
    df['state'] = df['vol_regime'].astype(str) + '_' + df['macro_state'].astype(str)
    
    # Stats
    print("\n4. Statistics:")
    print("\n   Macro State Distribution:")
    macro_dist = df['macro_state'].value_counts()
    for state, count in macro_dist.items():
        pct = (count / len(df)) * 100
        print(f"   {state:10s}: {count:5d} days ({pct:5.1f}%)")
    
    print("\n   9-State Distribution:")
    state_dist = df['state'].value_counts().sort_index()
    for state, count in state_dist.items():
        pct = (count / len(df)) * 100
        print(f"   {state:20s}: {count:5d} days ({pct:5.1f}%)")
    
    # Save
    print(f"\n5. Saving to {sys.argv[4]}...")
    df[['date', 'vol_regime', 'macro_state', 'state', 'crisis_regime', 'chop_regime']].to_csv(sys.argv[4], index=False)
    print("   ✓ Saved")
    print("\n" + "="*80)
    print("✓ COMPLETE")
    print("="*80)

if __name__ == '__main__':
    main()