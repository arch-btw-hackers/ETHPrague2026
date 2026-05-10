import '@rainbow-me/rainbowkit/styles.css';
import { getDefaultConfig } from '@rainbow-me/rainbowkit';
import { mainnet, base, sepolia } from 'wagmi/chains'; // Ensure sepolia is here
import { injectedWallet, rainbowWallet, walletConnectWallet } from '@rainbow-me/rainbowkit/wallets';

export const config = getDefaultConfig({
    appName: 'wallet-connect',
    projectId: 'e21c759ddabfdee2fce1c526b96833cd',
    chains: [mainnet, base, sepolia],
    ssr: false,
    wallets: [{
        groupName: 'Popular',
        wallets: [injectedWallet, rainbowWallet, walletConnectWallet],
    }],
});