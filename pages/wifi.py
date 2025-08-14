# pages/wifi.py
from dash import html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc

# 🎨 완전히 새로운 디자인의 Wi-Fi Connect 페이지
layout = html.Div([
    # 헤더 섹션
    html.Div([
        html.Div([
            html.Div("📶", style={
                'fontSize': '3rem',
                'marginBottom': '10px',
                'textAlign': 'center'
            }),
            html.H1("Wi-Fi Connect", 
                    style={
                        'color': 'white',
                        'fontWeight': 'bold',
                        'textAlign': 'center',
                        'margin': '0',
                        'fontSize': '2.5rem',
                        'textShadow': '2px 2px 4px rgba(0,0,0,0.3)'
                    }),
            html.P("무선 네트워크를 통한 디바이스 연결",
                   style={
                       'color': 'rgba(255,255,255,0.9)',
                       'textAlign': 'center',
                       'fontSize': '1.2rem',
                       'margin': '10px 0 0 0'
                   })
        ])
    ], style={
        'background': 'linear-gradient(135deg, #3498DB, #5DADE2)',
        'padding': '60px 20px',
        'marginBottom': '40px',
        'borderRadius': '0 0 30px 30px',
        'boxShadow': '0 10px 30px rgba(52, 152, 219, 0.3)'
    }),
    
    # 메인 컨테이너
    dbc.Container([
        # 연결 설정 카드
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Span("🔧", style={'fontSize': '1.5rem', 'marginRight': '10px'}),
                    html.Span("네트워크 연결 설정", style={'fontSize': '1.3rem', 'fontWeight': 'bold'})
                ])
            ], style={'backgroundColor': '#F8F9FA', 'border': 'none'}),
            
            dbc.CardBody([
                # 안내 메시지
                dbc.Alert([
                    html.Div([
                        html.Span("💡 ", style={'fontSize': '1.2rem'}),
                        html.Strong("연결 가이드: "),
                        "Master Device와 Slave Robot의 IP 주소와 포트를 정확히 입력하여 Wi-Fi 네트워크를 통해 연결하세요."
                    ])
                ], color="info", className="mb-4"),
                
                # Master Device 설정
                html.Div([
                    html.H5([
                        html.Span("🎮 ", style={'fontSize': '1.2rem'}),
                        "Master Device 설정"
                    ], style={'color': '#2C3E50', 'fontWeight': 'bold', 'marginBottom': '20px'}),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Label([
                                html.Span("🌐 ", style={'fontSize': '1rem'}),
                                "Master Device IP"
                            ], style={'fontSize': '1.1rem', 'fontWeight': 'bold'}),
                            dbc.Input(
                                id="master-ip", 
                                type="text", 
                                placeholder="예: 192.168.0.43",
                                style={
                                    'fontSize': '1.1rem',
                                    'height': '50px',
                                    'borderRadius': '10px',
                                    'border': '2px solid #E8F4FD',
                                    'transition': 'all 0.3s ease'
                                },
                                className="custom-input"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label([
                                html.Span("🔌 ", style={'fontSize': '1rem'}),
                                "Port"
                            ], style={'fontSize': '1.1rem', 'fontWeight': 'bold'}),
                            dbc.Input(
                                id="master-port", 
                                type="number", 
                                placeholder="예: 8081", 
                                min=1,
                                style={
                                    'fontSize': '1.1rem',
                                    'height': '50px',
                                    'borderRadius': '10px',
                                    'border': '2px solid #E8F4FD',
                                    'transition': 'all 0.3s ease'
                                },
                                className="custom-input"
                            )
                        ], width=6)
                    ], className="mb-4")
                ], style={
                    'backgroundColor': '#F8F9FA',
                    'padding': '25px',
                    'borderRadius': '15px',
                    'marginBottom': '30px',
                    'border': '1px solid #E8F4FD'
                }),
                
                # Slave Robot 설정
                html.Div([
                    html.H5([
                        html.Span("🤖 ", style={'fontSize': '1.2rem'}),
                        "Slave Robot 설정"
                    ], style={'color': '#2C3E50', 'fontWeight': 'bold', 'marginBottom': '20px'}),
                    
                    dbc.Row([
                        dbc.Col([
                            dbc.Label([
                                html.Span("🌐 ", style={'fontSize': '1rem'}),
                                "Slave Robot IP"
                            ], style={'fontSize': '1.1rem', 'fontWeight': 'bold'}),
                            dbc.Input(
                                id="wifi-ip", 
                                type="text", 
                                placeholder="예: 192.168.0.28",
                                style={
                                    'fontSize': '1.1rem',
                                    'height': '50px',
                                    'borderRadius': '10px',
                                    'border': '2px solid #E8F4FD',
                                    'transition': 'all 0.3s ease'
                                },
                                className="custom-input"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label([
                                html.Span("🔌 ", style={'fontSize': '1rem'}),
                                "Port"
                            ], style={'fontSize': '1.1rem', 'fontWeight': 'bold'}),
                            dbc.Input(
                                id="slave-port", 
                                type="number", 
                                placeholder="예: 5001", 
                                min=1,
                                style={
                                    'fontSize': '1.1rem',
                                    'height': '50px',
                                    'borderRadius': '10px',
                                    'border': '2px solid #E8F4FD',
                                    'transition': 'all 0.3s ease'
                                },
                                className="custom-input"
                            )
                        ], width=6)
                    ], className="mb-4")
                ], style={
                    'backgroundColor': '#F0F8FF',
                    'padding': '25px',
                    'borderRadius': '15px',
                    'marginBottom': '30px',
                    'border': '1px solid #D6EAF8'
                }),
                
                # 상태 표시
                html.Div(id="show-wifi-info", className="mb-4"),
                
                # 연결 버튼
                html.Div([
                    dbc.Button([
                        html.Span("🚀 ", style={'fontSize': '1.3rem', 'marginRight': '10px'}),
                        "Wi-Fi 연결하기"
                    ], 
                    id="btn-wifi-connect", 
                    color="primary",
                    size="lg",
                    style={
                        'width': '100%',
                        'height': '60px',
                        'fontSize': '1.3rem',
                        'fontWeight': 'bold',
                        'borderRadius': '15px',
                        'background': 'linear-gradient(135deg, #3498DB, #5DADE2)',
                        'border': 'none',
                        'boxShadow': '0 5px 15px rgba(52, 152, 219, 0.3)',
                        'transition': 'all 0.3s ease'
                    },
                    className="connect-button")
                ], className="text-center mb-4")
            ], style={'padding': '30px'})
        ], style={
            'boxShadow': '0 10px 30px rgba(0,0,0,0.1)',
            'border': 'none',
            'borderRadius': '20px',
            'marginBottom': '30px'
        }),
        
        # 연결 정보 및 상태 카드
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Span("📊", style={'fontSize': '1.5rem', 'marginRight': '10px'}),
                    html.Span("연결 정보 및 상태", style={'fontSize': '1.3rem', 'fontWeight': 'bold'})
                ])
            ], style={'backgroundColor': '#F8F9FA', 'border': 'none'}),
            
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.H5("🔧 프로토콜 설정", className="mb-3"),
                            html.P([html.Strong("통신 방식: "), "gRPC"]),
                            html.P([html.Strong("프로토콜: "), "HTTP/2"]),
                            html.P([html.Strong("인증: "), "Insecure Channel"]),
                            html.P([html.Strong("타임아웃: "), "5초"])
                        ])
                    ], width=6),
                    dbc.Col([
                        html.Div([
                            html.H5("📈 네트워크 상태", className="mb-3"),
                            html.P([
                                html.Span("🔴", id="wifi-status-led", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                                html.Span("연결 대기 중", id="wifi-status-text")
                            ]),
                            html.P([html.Strong("네트워크: "), "Wi-Fi"]),
                            html.P([html.Strong("대역폭: "), "고속"]),
                            html.P([html.Strong("보안: "), "WPA2/WPA3"])
                        ])
                    ], width=6)
                ])
            ])
        ], style={
            'boxShadow': '0 10px 30px rgba(0,0,0,0.1)',
            'border': 'none',
            'borderRadius': '20px',
            'marginBottom': '30px'
        }),
        
        # 네트워크 설정 도움말 카드
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Span("❓", style={'fontSize': '1.5rem', 'marginRight': '10px'}),
                    html.Span("설정 도움말", style={'fontSize': '1.3rem', 'fontWeight': 'bold'})
                ])
            ], style={'backgroundColor': '#F8F9FA', 'border': 'none'}),
            
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.H6("🌐 IP 주소 찾기", className="mb-2"),
                        html.Small("• Windows: cmd → ipconfig", className="d-block"),
                        html.Small("• Linux/Mac: ifconfig 또는 ip addr", className="d-block"),
                        html.Small("• 라즈베리파이: hostname -I", className="d-block")
                    ], width=6),
                    dbc.Col([
                        html.H6("🔌 포트 설정", className="mb-2"),
                        html.Small("• Master Device: 8081 (기본값)", className="d-block"),
                        html.Small("• Slave Robot: 5001 (기본값)", className="d-block"),
                        html.Small("• 방화벽에서 포트 허용 필요", className="d-block")
                    ], width=6)
                ])
            ])
        ], style={
            'boxShadow': '0 10px 30px rgba(0,0,0,0.1)',
            'border': 'none',
            'borderRadius': '20px',
            'marginBottom': '30px',
            'backgroundColor': '#FDFDFE'
        }),
        
        # 하단 네비게이션
        html.Div([
            dcc.Link([
                html.Span("🏠 ", style={'fontSize': '1.2rem'}),
                "메인으로 돌아가기"
            ], 
            href="/", 
            className="btn btn-outline-primary btn-lg",
            style={
                'borderRadius': '15px',
                'fontWeight': 'bold',
                'textDecoration': 'none',
                'padding': '12px 30px',
                'transition': 'all 0.3s ease'
            })
        ], className="text-center mb-5")
        
    ], fluid=True, style={'maxWidth': '1200px', 'margin': '0 auto'})
    
], className="fade-in", style={
    'background': 'linear-gradient(to bottom, #F8F9FA, #FFFFFF)',
    'minHeight': '100vh'
})

# CSS 스타일을 추가하기 위한 스타일 함수
def get_css_styles():
    return """
    .custom-input:focus {
        border-color: #3498DB !important;
        box-shadow: 0 0 0 0.2rem rgba(52, 152, 219, 0.25) !important;
    }
    
    .connect-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(52, 152, 219, 0.4) !important;
    }
    
    .fade-in {
        animation: fadeIn 0.5s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .connection-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(0,0,0,0.15) !important;
    }
    """