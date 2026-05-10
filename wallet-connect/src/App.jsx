import { useState } from 'react';
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { CONTRACT_ADDRESS, CONTRACT_ABI, STATIC_RECEIVER, TRACKER_SERVICE_WALLET, API_BASE } from './constants';
import './App.css';

function App() {
  const { isConnected } = useAccount();
  const [status, setStatus] = useState('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [txHash, setTxHash] = useState('');

  const { data: hash, writeContract, isPending } = useWriteContract();

  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  const handleConfirm = async () => {
    setStatus('calling_api');
    setErrorMsg('');

    try {
      const res = await fetch(`${API_BASE}/packages/initialize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          temp_c: 4.5,
          acceleration: 0.12,
        }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`API error ${res.status}: ${errBody}`);
      }

      const data = await res.json();

      setTxHash(data.tx_hash);

      setStatus('sending_tx');

      writeContract({
        address: CONTRACT_ADDRESS,
        abi: CONTRACT_ABI,
        functionName: 'createShipment',
        args: [
          STATIC_RECEIVER,
          TRACKER_SERVICE_WALLET,
          data.package_ref,
        ],
      });

      setStatus('confirming');
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  const isBusy = status === 'calling_api' || isPending || isConfirming;

  const buttonLabel = () => {
    if (status === 'calling_api') return 'Initializing...';
    if (isPending) return 'Confirm in Wallet...';
    if (isConfirming) return 'Processing...';
    return 'Confirm';
  };

  return (
    <section id="center">
      <h1>Delivery Payment Portal</h1>
      <ConnectButton />

      {isConnected && (
        <div style={{ marginTop: '30px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <button
            onClick={handleConfirm}
            className="counter"
            disabled={isBusy || isSuccess}
          >
            {buttonLabel()}
          </button>

          {isSuccess && <p style={{ color: 'green' }}>Payment Confirmed!</p>}
          {txHash && <p>API tx_hash: <code>{txHash}</code></p>}
          {status === 'error' && <p style={{ color: 'red' }}>{errorMsg}</p>}
        </div>
      )}
    </section>
  );
}

export default App;