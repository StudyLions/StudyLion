from .stats import stats_page
from .profile import profile_page
from .summary import summary_page
from .weekly import weekly_page
from .monthly import monthly_page
from .weekly_goals import weekly_goal_page
from .monthly_goals import monthly_goal_page
from .leaderboard import leaderboard_page


pages = [
    profile_page, stats_page,
    weekly_page, monthly_page,
    weekly_goal_page, monthly_goal_page,
    leaderboard_page,
]
