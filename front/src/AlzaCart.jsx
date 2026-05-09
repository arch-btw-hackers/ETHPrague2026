import React from 'react';
import './AlzaCart.css';

const AlzaCart = () => {
    return (
        <div className="alza-cz">
            <header className="header-alz-9u9iou-10">
                <div className="header-alz-8v7ev0-11">
                    <div className="header-alz-71zeas-15">
                        <img src="https://cdn.alza.cz/images/web-static/eshop-logos/alza_cz.svg" alt="Alza.cz" style={{ height: '40px' }} />
                    </div>

                    <div className="header-alz-fzim95-17">
                        <div className="header-alz-9t7adh-45" style={{ position: 'relative' }}>
                            <span className="header-search-icon-inside">🔍</span>
                            <input className="header-alz-xigua8-53" placeholder="Co hledáte? Např. kabel AlzaPower..." type="text" />
                            <button className="header-alz-14zbaw-58 blue">Hledat</button>
                        </div>
                    </div>

                    <div className="header-right-side">
                        <div className="header-alz-xafhyl-61">
                            <div className="header-alz-wnfgr4-68">👤</div>
                            <div className="header-alz-9seg3b-63">
                                <span className="header-alz-lswn9v-64">Moje Alza</span>
                                <span className="header-alz-uyx6yg-67">Přihlásit se</span>
                            </div>
                        </div>

                        <div className="header-alz-iyrci5-24">
                            <span className="header-icon-link">📋</span>
                            <span className="header-icon-link">❤️</span>
                            <img className="header-alz-ykjmzy-119" src="https://cdn.alza.cz/images/web-static/languages/cz.png" alt="CZ" />
                            <span className="header-icon-link" style={{ color: '#a4a4a4' }}>🛒</span>
                        </div>
                    </div>
                </div>
            </header>

            <main className="main-card">
                <nav className="order-nav">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="order1-alz-oe88l6-44 order1-alz-tzaf2l-45">1</span>
                        <span style={{ color: '#0094E7', fontWeight: 'bold' }}>Košík</span>
                    </div>
                    <div style={{ width: '60px', height: '2px', background: '#c6c6c6' }}></div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="order1-alz-oe88l6-44">2</span>
                        <span style={{ color: '#6E6E6E' }}>Doprava a platba</span>
                    </div>
                </nav>

                <div className="empty-cart-box">
                    <img src="https://cdn.alza.cz/Styles/full/images/bg-basket-empty.png" alt="" style={{ width: '60px', marginRight: '20px' }} />
                    <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 'bold' }}>Jsem tak prázdný...</span>
                        <a href="/" style={{ color: '#00275B', fontWeight: 'bold', textDecoration: 'none' }}>Zobrazit katalog</a>
                    </div>
                </div>

                <div className="charity-section">
                    <span style={{ fontWeight: 'bold', display: 'block', marginBottom: '15px' }}>Přispějte na dobrou věc</span>
                    <div style={{ display: 'flex', gap: '15px' }}>
                        <img src="https://image.alza.cz/products/XX222b/XX222b.jpg?width=87&height=87" alt="" style={{ width: '70px', height: '70px' }} />
                        <div style={{ flex: 1 }}>
                            <select style={{ width: '100%', padding: '6px', marginBottom: '10px' }}>
                                <option>Aloisovy ponožky - 180 Kč</option>
                            </select>
                            <button style={{ float: 'right', padding: '6px 15px', background: '#f4f5f5', border: '1px solid #ccc', borderRadius: '4px' }}>Vložit</button>
                        </div>
                    </div>
                </div>

                <div style={{ clear: 'both', padding: '40px 30px', display: 'flex', justifyContent: 'space-between', borderTop: '1px dotted #e0e0e0' }}>
                    <button style={{ padding: '10px 20px', background: '#fff', border: '1px solid #e0e0e0', borderRadius: '4px', fontWeight: 'bold', color: '#00275B' }}>
                        ◀ Zpět к nákupu
                    </button>
                    <div style={{ textAlign: 'right' }}>
                        <span style={{ fontSize: '12px', color: '#6E6E6E', display: 'block' }}>Cena к úhradě:</span>
                        <span style={{ fontSize: '28px', fontWeight: 'bold' }}>0 Kč</span>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default AlzaCart;