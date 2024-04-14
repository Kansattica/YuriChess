import chess

class YuriChessState:

		# When maximize_yuri is false, we want the engine to be kind of the opposite of the default maximize_yuri setting.
		# That also means that we want to invert the weights by subtracting them all from the maximum weight.
		# Fun fact: doing this with multiplication means the weights get way too big for the silly weight repeat thing we do.
		def total_weights(self):
			return self.novel_move_weight + self.check_weight + self.checkmate_weight+  self.capture_weight + self.en_passant_weight + self.promotion_weight + self.queens_kissing_weight + self.castling_weight + self.attack_weight + self.attacked_weight + self.safety_weight + self.pin_weight + self.woman_respecting_weight + self.woman_disrespecting_weight + self.horse_appreciation_weight

		def min_or_max(self):
			return max if self.maximize_yuri else min
		
		def __init__(self):
			self.do_debug = False
			self.current_board = chess.Board()
			self.maximize_yuri = True
			self.last_best_move = None
			self.current_eval_func = lambda x: x["Sum"]
			self.backup_eval_func = lambda x: x["BonusSum"]
			self.bonus_backup_eval_func = lambda x: x["ReverseBonusSum"]
			self.novel_move_weight = 2
			self.check_weight = 1
			self.checkmate_weight = 3
			self.capture_weight = 1
			self.en_passant_weight = 2
			self.promotion_weight = 2
			self.queens_kissing_weight = 5
			self.castling_weight = 2
			self.attack_weight = 1
			self.attacked_weight = 1
			self.safety_weight = 1
			self.pin_weight = 1
			self.woman_respecting_weight = 5
			self.woman_disrespecting_weight = 1
			self.horse_appreciation_weight = 3
			self.yuri_weight = False

