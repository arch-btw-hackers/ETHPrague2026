import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { CONTRACT_ADDRESS, CONTRACT_ABI, STATIC_RECEIVER, TRACKER_SERVICE_WALLET, API_BASE } from './constants';
import './AlzaPayment.css';

const AlzaPayment = () => {
    const navigate = useNavigate();
    const { address, isConnected } = useAccount();

    const [temp, setTemp] = useState('23');
    const [overload, setOverload] = useState('5');
    const [status, setStatus] = useState('');

    const { data: hash, writeContractAsync, isPending } = useWriteContract();
    const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

    const handleAuthAndSend = async () => {
        if (!isConnected) {
            alert("Please connect your wallet first!");
            return;
        }

        try {
            setStatus('Initializing package...');

            const res = await fetch(`${API_BASE}/packages/initialize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    temp_c: parseFloat(temp),
                    acceleration: parseFloat(overload),
                }),
            });

            if (!res.ok) {
                const errBody = await res.text();
                throw new Error(`API error ${res.status}: ${errBody}`);
            }

            const data = await res.json();

            setStatus('Confirm in wallet...');

            const txHash = await writeContractAsync({
                address: CONTRACT_ADDRESS,
                abi: CONTRACT_ABI,
                functionName: 'createShipment',
                args: [
                    STATIC_RECEIVER,
                    TRACKER_SERVICE_WALLET,
                    data.package_ref,
                ],
            });
        } catch (error) {
            setStatus(`Error: ${error.shortMessage || error.message || 'Transaction failed'}`);
        }
    };

    return (
        <div className="alza-checkout-page">
            <header className="header-alz-8v7ev0-11">
                <div className="header-content">
                    <img src="https://cdn.alza.cz/images/web-static/eshop-logos/alza_cz.svg" alt="Alza" style={{ height: '40px' }} />
                    <div className="search-container">
                        <input type="text" placeholder="What are you looking for?" />
                        <button>Search</button>
                    </div>
                    <div className="header-right">
                        <div style={{ textAlign: 'right', fontSize: '13px' }}>
                            <b style={{ display: 'block' }}>My Alza</b>
                            <span style={{ color: '#00275B' }}>Sign in</span>
                        </div>
                        <img src="https://cdn.alza.cz/images/web-static/languages/cz.png" alt="CZ" style={{ width: '22px', borderRadius: '50%' }} />
                        <div style={{ position: 'relative', fontSize: '20px' }}>
                            🛒 <span style={{ position: 'absolute', top: '-8px', right: '-8px', background: '#e9242e', color: 'white', borderRadius: '50%', padding: '2px 5px', fontSize: '10px' }}>1</span>
                        </div>
                    </div>
                </div>
            </header>

            <main className="main-container">
                <div className="left-column">
                    <nav className="order-nav">
                        <div className="order-step completed">
                            <span className="order-step-num">✓</span> <span>Cart</span>
                        </div>
                        <div className="nav-line" style={{ background: '#0094E7' }}></div>
                        <div className="order-step active">
                            <span className="order-step-num">2</span> <span>Shipping & Payment</span>
                        </div>
                        <div className="nav-line"></div>
                        <div className="order-step">
                            <span className="order-step-num">3</span> <span>Delivery Details</span>
                        </div>
                    </nav>

                    <div className="alza-plus-banner">
                        <div className="alza-plus-info">
                            <img src="https://cdn.alza.cz/Foto/ImgGalery/LandingPages/AlzaPlus/Logo-AlzaPlus.svg" alt="AlzaPlus" style={{ height: '24px', marginBottom: '10px' }} />
                            <h3 style={{ margin: '0 0 10px 0' }}>Enjoy free delivery with AlzaPlus+</h3>
                            <p style={{ fontSize: '13px', margin: '0 0 15px 0', color: '#555' }}>Get free delivery on all orders to AlzaBoxes, stores, and pickup points.</p>
                            <button className="btn-ap-white">Not interested</button>
                            <button className="btn-ap-blue">Annual - 25 CZK / mo</button>
                        </div>
                        <img src="https://image.alza.cz/Foto/Domains/Logistics/AlzaPlus/alzak_holding_plus.png" className="alza-plus-mascot" alt="Mascot" />
                    </div>

                    <h2 className="section-title">Choose delivery method</h2>
                    <div className="selection-group">
                        <div className="selection-row">
                            <input type="radio" name="delivery" defaultChecked />
                            <img src="https://image.alza.cz/Foto/Domains/Logistics/PersonalPickup/svg/icon-2.svg" className="row-icon" alt="" />
                            <span className="row-label">AlzaBox - self-service pickup boxes</span>
                            <span className="row-price">from 49 CZK</span>
                            <span className="row-delivery-time">tomorrow by 9:00</span>
                        </div>
                    </div>


                    <h2 className="section-title">Transport Conditions</h2>
                    <div className="alza-conditions-box">
                        <div className="alza-input-row">
                            <label>Temperature (°C)</label>
                            <input
                                type="number"
                                value={temp}
                                onChange={(e) => setTemp(e.target.value)}
                                className="alza-custom-input"
                            />
                        </div>
                        <div className="alza-input-row">
                            <label>Acceleration Overload</label>
                            <input
                                type="number"
                                value={overload}
                                onChange={(e) => setOverload(e.target.value)}
                                className="alza-custom-input"
                            />
                        </div>
                    </div>

                    <h2 className="section-title">Choose payment</h2>
                    <div className="selection-group">
                        <div className="selection-row">
                            <input type="radio" name="payment" />
                            <img src="https://cdn.alza.cz/Foto/ImgGalery/IkonyKosik2/svg/platba/apple-pay.svg" className="row-icon" alt="" />
                            <span className="row-label">Apple Pay</span>
                            <span className="row-price" style={{ color: '#689700' }}>free</span>
                        </div>

                        <div className="selection-row wallet-row">
                            <input type="radio" name="payment" defaultChecked />
                            <div className="row-icon wallet-icon">🌐</div>
                            <div className="row-label wallet-label-container">
                                <span className="row-label">Crypto Wallet</span>
                                <div className="wallet-button-wrapper">
                                    <ConnectButton showBalance={false} chainStatus="none" accountStatus="avatar" />
                                </div>
                            </div>
                            <span className="row-price" style={{ color: '#689700' }}>free</span>
                        </div>
                    </div>

                    <div className="footer-actions">
                        <button className="btn-back" onClick={() => navigate('/alza')}>Back</button>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                            {(status || isSuccess) && (
                                <div className="alza-status-text" style={{
                                    color: isSuccess ? 'green' : status.includes('Error') ? 'red' : 'inherit',
                                    textAlign: 'right',
                                    fontSize: isSuccess ? '15px' : undefined,
                                    marginBottom: '10px'
                                }}>
                                    {isSuccess ? (
                                        <div style={{ textAlign: 'right' }}>
                                            <strong style={{ display: 'block', marginBottom: '8px', fontSize: '15px', color: 'green' }}>Shipment created on-chain!</strong>
                                            <div style={{ display: 'inline-block', color: '#555', fontSize: '14px', lineHeight: '1.5' }}>
                                                You can view status of your package
                                                <button
                                                    onClick={() => window.open('https://protozoan-mankind-rogue.ngrok-free.dev/', '_blank')}
                                                    style={{
                                                        marginLeft: '8px',
                                                        marginTop: '15px',
                                                        marginBottom: '15px',
                                                        padding: '4px 12px',
                                                        backgroundColor: '#0094E7',
                                                        color: 'white',
                                                        border: 'none',
                                                        borderRadius: '4px',
                                                        cursor: 'pointer',
                                                        fontWeight: 'bold',
                                                        whiteSpace: 'nowrap'
                                                    }}
                                                >
                                                    here
                                                </button>
                                            </div>
                                        </div>
                                    ) : status}
                                </div>
                            )}
                            <button
                                className="btn-confirm"
                                onClick={handleAuthAndSend}
                                disabled={!isConnected || isPending || isConfirming || isSuccess}
                                style={{ opacity: (!isConnected || isPending || isConfirming) ? 0.6 : 1 }}
                            >
                                {!isConnected ? "Connect Wallet"
                                    : isPending ? "Confirm in Wallet..."
                                        : isConfirming ? "Processing..."
                                            : isSuccess ? "Payment Confirmed ✓"
                                                : "Continue ▶"}
                            </button>
                        </div>
                    </div>
                </div>

                <aside className="right-column">
                    <div className="summary-card">
                        <h3 style={{ fontSize: '16px', margin: '0 0 15px 0', borderBottom: '1px solid #eee', paddingBottom: '10px' }}>Order Summary</h3>
                        <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', fontSize: '18px' }}>
                            <span>Total</span>
                            <span>0 CZK</span>
                        </div>
                    </div>
                </aside>
            </main>
        </div>
    );
};

export default AlzaPayment;