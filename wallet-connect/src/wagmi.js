import '@rainbow-me/rainbowkit/styles.css';
import { getDefaultConfig } from '@rainbow-me/rainbowkit';
import { mainnet, base } from 'wagmi/chains';

export const config = getDefaultConfig({
    appName: 'wallet-connect',
    projectId: 'e21c759ddabfdee2fce1c526b96833cd',
    chains: [mainnet, base],
    ssr: false,
});