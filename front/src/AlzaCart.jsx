import React from 'react';
import { useNavigate } from 'react-router-dom';
import './AlzaCart.css';

const AlzaCart = () => {
    const navigate = useNavigate();

    return (
        <div className="alza-cz">
            <header className="header-alz-9u9iou-10">
                <div className="header-alz-8v7ev0-11">
                    <div className="header-alz-71zeas-15">
                        <img src="https://cdn.alza.cz/images/web-static/eshop-logos/alza_cz.svg" alt="Alza" style={{ height: '40px' }} />
                    </div>

                    <div className="header-alz-fzim95-17">
                        <div className="header-alz-9t7adh-45">
                            <input
                                className="header-alz-xigua8-53"
                                placeholder="What are you looking for?"
                                type="text"
                            />
                            <button className="header-alz-14zbaw-58">Search</button>
                        </div>
                    </div>

                    <div className="header-right-side">
                        <div className="header-alz-xafhyl-61">
                            <div className="user-avatar-container">
                                <svg viewBox="0 0 24 24" className="alza-svg-icon" style={{ width: '20px' }}>
                                    <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
                                </svg>
                            </div>
                            <div className="header-alz-9seg3b-63">
                                <span className="user-name-text">My Alza</span>
                                <span className="sign-in-text">Sign in</span>
                            </div>
                            <span style={{ fontSize: '10px', marginLeft: '4px', color: '#999' }}>▼</span>
                        </div>

                        <div className="icon-separator"></div>

                        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
                            <svg viewBox="0 0 24 24" className="alza-svg-icon"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14l-4-4 1.41-1.41L10 14.17l5.59-5.59L17 10l-3 7z" /></svg>
                            <svg viewBox="0 0 24 24" className="alza-svg-icon"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 2 7.5 2c1.74 0 3.41.81 4.5 2.09C13.09 2.81 14.76 2 16.5 2 19.58 2 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" /></svg>
                            <img src="https://cdn.alza.cz/images/web-static/languages/cz.png" alt="CZ" style={{ width: '22px', height: '22px', borderRadius: '50%' }} />
                        </div>

                        <div className="icon-separator"></div>

                        <svg viewBox="0 0 24 24" className="cart-icon-gray"><path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.27.12-.41 0-.55-.45-1-1-1H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z" /></svg>
                    </div>
                </div>
            </header>

            <main className="main-card">
                <div className="order-nav">
                    <div className="order-step active">
                        <span className="order-step-num">1</span> <span>Cart</span>
                    </div>
                    <div className="nav-line"></div>
                    <div className="order-step">
                        <span className="order-step-num">2</span> <span>Shipping & Payment</span>
                    </div>
                    <div className="nav-line"></div>
                    <div className="order-step">
                        <span className="order-step-num">3</span> <span>Delivery Details</span>
                    </div>
                </div>

                <div className="empty-cart-box">
                    <img src="https://cdn.alza.cz/Styles/full/images/bg-basket-empty.png" alt="" style={{ width: '60px', marginRight: '20px' }} />
                    <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontWeight: 'bold' }}>I am so empty...</span>
                        <a href="/" style={{ color: 'var(--alza-dark-blue)', fontWeight: 'bold', textDecoration: 'none' }}>View catalog</a>
                    </div>
                </div>

                <div style={{ color: 'var(--alza-light-blue)', cursor: 'pointer', fontSize: '14px', marginBottom: '30px' }}>
                    ❯ Use a discount / gift voucher
                </div>



                <div className="footer-actions">
                    <button className="btn-back">◀ Back to shopping</button>
                    <div className="price-container">
                        <div style={{ fontSize: '12px', color: '#666' }}>Total price with VAT:</div>
                        <div style={{ fontSize: '32px', fontWeight: 'bold' }}>0 CZK</div>
                        <button className="btn-continue" onClick={() => navigate('/alza-payment')}>
                            Continue ▶
                        </button>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default AlzaCart;