from django.urls import path
from . import views

urlpatterns = [
    path('login', views.MemberLoginView.as_view(), name='login'),
    path('register', views.MemberRegisterView.as_view(), name='register'),
    path('members/me', views.MemberMeView.as_view(), name='member-me'),
    path('members/<int:pk>/public', views.MemberPublicView.as_view(), name='member-public'),
    path('members/<int:pk>/insights', views.MemberInsightsView.as_view(), name='insights'),

    path('members', views.MemberListView.as_view(), name='member-list'),
    path('members/<int:pk>', views.MemberDetailView.as_view(), name='member-detail'),
    path('members/<int:pk>/export', views.MemberDownlineExportView.as_view(), name='member-export'),
    path('stats', views.SystemStatsView.as_view(), name='stats'),
    path('stats/reports', views.ReportStatsView.as_view(), name='report-stats'),
    path('invites', views.InviteCreateView.as_view(), name='invite-create'),
    path('invites/<uuid:id>', views.InviteDetailView.as_view(), name='invite-detail'),
    path('voter-records', views.VoterRecordListView.as_view(), name='voter-records'),
]
