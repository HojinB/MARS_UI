# pages/usb.py
from dash import html, dcc, Input, Output, callback
import dash_bootstrap_components as dbc
import serial.tools.list_ports

def get_com_ports():
    """실시간으로 COM 포트 목록을 가져오는 함수"""
    try:
        ports = []
        available_ports = list(serial.tools.list_ports.comports())
        
        if not available_ports:
            return [{"label": "🚫 사용 가능한 COM 포트가 없습니다", "value": "", "disabled": True}]
        
        for p in available_ports:
            # 포트 설명을 더 간결하고 읽기 쉽게 정리
            description = p.description
            
            # 일반적인 불필요한 정보 제거 및 한국어화
            if "USB Serial Port" in description:
                description = "USB 시리얼 포트"
            elif "USB-SERIAL CH340" in description:
                description = "CH340 USB 시리얼"
            elif "Silicon Labs CP210x" in description:
                description = "CP210x USB 시리얼"
            elif "FTDI" in description:
                description = "FTDI USB 시리얼"
            elif "Arduino" in description:
                description = "Arduino 장치"
            elif len(description) > 35:
                description = description[:32] + "..."
            
            # 포트 이름과 간결한 설명으로 구성
            label = f"{p.device} — {description}"
            
            ports.append({
                "label": label, 
                "value": p.device
            })
        
        # 포트 번호순으로 정렬 (COM1, COM2, COM3...)
        ports.sort(key=lambda x: int(''.join(filter(str.isdigit, x['value'])) or '0'))
        return ports
    except Exception as e:
        print(f"포트 스캔 오류: {e}")
        return [{"label": "❌ 포트 스캔 중 오류 발생", "value": "", "disabled": True}]

# 🎨 완전히 새로운 디자인의 USB Connect 페이지
layout = html.Div([
    # 헤더 섹션
    html.Div([
        html.Div([
            html.Div("🔌", style={
                'fontSize': '3rem',
                'marginBottom': '10px',
                'textAlign': 'center'
            }),
            html.H1("USB Connect", 
                    style={
                        'color': 'white',
                        'fontWeight': 'bold',
                        'textAlign': 'center',
                        'margin': '0',
                        'fontSize': '2.5rem',
                        'textShadow': '2px 2px 4px rgba(0,0,0,0.3)'
                    }),
            html.P("USB 시리얼 포트를 통한 직접 연결",
                   style={
                       'color': 'rgba(255,255,255,0.9)',
                       'textAlign': 'center',
                       'fontSize': '1.2rem',
                       'margin': '10px 0 0 0'
                   })
        ])
    ], style={
        'background': 'linear-gradient(135deg, #E67E22, #F39C12)',
        'padding': '60px 20px',
        'marginBottom': '40px',
        'borderRadius': '0 0 30px 30px',
        'boxShadow': '0 10px 30px rgba(230, 126, 34, 0.3)'
    }),
    
    # 메인 컨테이너
    dbc.Container([
        # 포트 선택 카드
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Span("📡", style={'fontSize': '1.5rem', 'marginRight': '10px'}),
                    html.Span("시리얼 포트 선택", style={'fontSize': '1.3rem', 'fontWeight': 'bold'})
                ])
            ], style={'backgroundColor': '#F8F9FA', 'border': 'none'}),
            
            dbc.CardBody([
                # 안내 메시지
                dbc.Alert([
                    html.Div([
                        html.Span("💡 ", style={'fontSize': '1.2rem'}),
                        html.Strong("사용 가이드: "),
                        "마스터 디바이스를 USB로 연결한 후 해당 COM 포트를 선택하세요."
                    ])
                ], color="info", className="mb-4"),
                
                # 포트 선택 섹션
                html.Div([
                    html.Label([
                        html.Span("🔍 ", style={'fontSize': '1.1rem'}),
                        "COM 포트 검색 및 선택"
                    ], style={'fontSize': '1.1rem', 'fontWeight': 'bold', 'marginBottom': '15px', 'display': 'block'}),
                    
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                id="usb-port-dropdown",
                                options=get_com_ports(),
                                placeholder="🔌 COM 포트를 선택하세요",
                                style={
                                    'fontSize': '1.1rem',
                                    'minHeight': '50px',
                                    'position': 'relative',
                                    'zIndex': '1000'
                                },
                                maxHeight=300,  # 드롭다운 최대 높이 증가
                                className="custom-dropdown",
                                # 드롭다운 메뉴를 body에 직접 렌더링하여 z-index 문제 해결
                                optionHeight=50
                            )
                        ], width=8, style={'position': 'relative', 'zIndex': '1000'}),
                        dbc.Col([
                            dbc.Button([
                                html.Span("🔄 ", style={'fontSize': '1.1rem'}),
                                "새로고침"
                            ], 
                            id="refresh-ports-btn", 
                            color="secondary", 
                            size="lg",
                            style={
                                'width': '100%',
                                'height': '50px',
                                'borderRadius': '10px',
                                'fontWeight': 'bold'
                            })
                        ], width=4)
                    ], className="mb-4"),
                    
                    # 상태 표시
                    html.Div(id="usb-connect-status", className="mb-4"),
                    
                    # 연결 버튼
                    html.Div([
                        dbc.Button([
                            html.Span("⚡ ", style={'fontSize': '1.3rem', 'marginRight': '10px'}),
                            "연결하기"
                        ], 
                        id="btn-usb-connect", 
                        color="warning",
                        size="lg",
                        style={
                            'width': '100%',
                            'height': '60px',
                            'fontSize': '1.3rem',
                            'fontWeight': 'bold',
                            'borderRadius': '15px',
                            'background': 'linear-gradient(135deg, #E67E22, #F39C12)',
                            'border': 'none',
                            'boxShadow': '0 5px 15px rgba(230, 126, 34, 0.3)',
                            'transition': 'all 0.3s ease'
                        },
                        className="connect-button")
                    ], className="text-center mb-4")
                ], style={'padding': '20px'})
            ], className="dropdown-card-body")
        ], style={
            'boxShadow': '0 10px 30px rgba(0,0,0,0.1)',
            'border': 'none',
            'borderRadius': '20px',
            'marginBottom': '30px',
            'position': 'relative',
            'zIndex': '100'
        }, className="dropdown-card"),
        
        # 연결 정보 카드
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Span("📋", style={'fontSize': '1.5rem', 'marginRight': '10px'}),
                    html.Span("연결 정보", style={'fontSize': '1.3rem', 'fontWeight': 'bold'})
                ])
            ], style={'backgroundColor': '#F8F9FA', 'border': 'none'}),
            
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.H5("🔧 설정", className="mb-3"),
                            html.P([html.Strong("Baud Rate: "), "4,000,000"]),
                            html.P([html.Strong("Data Bits: "), "8"]),
                            html.P([html.Strong("Stop Bits: "), "1"]),
                            html.P([html.Strong("Parity: "), "None"])
                        ])
                    ], width=6),
                    dbc.Col([
                        html.Div([
                            html.H5("📈 상태", className="mb-3"),
                            html.P([
                                html.Span("🔴", id="connection-status-led", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                                html.Span("연결 대기 중", id="connection-status-text")
                            ]),
                            html.P([html.Strong("프로토콜: "), "Binary"]),
                            html.P([html.Strong("통신 방식: "), "시리얼"]),
                            html.P([html.Strong("타임아웃: "), "0.1초"])
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
        
    ], fluid=True, style={'maxWidth': '1200px', 'margin': '0 auto', 'overflow': 'visible', 'position': 'relative', 'zIndex': '50'})
    
], className="fade-in")

# 포트 새로고림 콜백
@callback(
    Output("usb-port-dropdown", "options"),
    Input("refresh-ports-btn", "n_clicks")
)
def refresh_ports(n_clicks):
    return get_com_ports()