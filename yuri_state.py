import chess

class YuriChessState:
		def __init__(self):
			self.do_debug = False
			self.current_board = chess.Board()
			self.min_or_max = max
			self.last_best_move = None
			self.current_eval_func = lambda x: x["Sum"]
			self.backup_eval_func = lambda x: x["BonusSum"]
			self.bonus_backup_eval_func = lambda x: x["ReverseBonusSum"]
			self.novel_move_weight = 2
			self.check_weight = 0
			self.checkmate_weight = 3
			self.capture_weight = 0
			self.en_passant_weight = 2

