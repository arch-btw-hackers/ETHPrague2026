import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import './AlzaPayment.css';

const AlzaPayment = () => {
    const navigate = useNavigate();

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
                            <input type="radio" name="delivery" />
                            <img src="https://image.alza.cz/Foto/Domains/Logistics/PersonalPickup/svg/icon-2.svg" className="row-icon" alt="" />
                            <span className="row-label">AlzaBox - self-service pickup boxes</span>
                            <span className="row-price">from 49 CZK</span>
                            <span className="row-delivery-time">tomorrow by 9:00</span>
                        </div>
                        <div className="selection-row">
                            <input type="radio" name="delivery" />
                            <img src="https://cdn.alza.cz/Foto/ImgGalery/IkonyKosik2/svg/delivery/prodejna.svg" className="row-icon" alt="" />
                            <span className="row-label">Showroom Prague 7 Holesovice</span>
                            <span className="row-price">free or 45 CZK</span>
                            <span className="row-delivery-time">tomorrow by 8:30</span>
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
                        <div className="selection-row">
                            <input type="radio" name="payment" />
                            <img src="https://cdn.alza.cz/Foto/ImgGalery/IkonyKosik2/svg/platba/karta.svg" className="row-icon" alt="" />
                            <span className="row-label">Card online</span>
                            <span className="row-price" style={{ color: '#689700' }}>free</span>
                        </div>

                        {/* Новая строка с кошельком */}
                        <div className="selection-row wallet-row">
                            <input type="radio" name="payment" />
                            <div className="row-icon wallet-icon"></div>
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
                        <button className="btn-confirm">Continue ▶</button>
                    </div>
                </div>

                <aside className="right-column">
                    <div className="summary-card">
                        <h3 style={{ fontSize: '16px', margin: '0 0 15px 0', borderBottom: '1px solid #eee', paddingBottom: '10px' }}>Order Summary</h3>
                        <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                            <img src="https://image.alza.cz/products/PLT554a/PLT554a.jpg?width=87&height=87" alt="" style={{ width: '40px', height: '40px' }} />
                            <div style={{ fontSize: '12px' }}>
                                1x PILOT FriXion Ball 07 blue
                                <div style={{ fontWeight: 'bold', marginTop: '4px' }}>69 CZK</div>
                            </div>
                        </div>
                        <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', fontSize: '18px' }}>
                            <span>Total</span>
                            <span>69 CZK</span>
                        </div>
                    </div>
                </aside>
            </main>
        </div>
    );
};

export default AlzaPayment;