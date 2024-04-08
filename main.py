import sys
import chess

from yuri_db import calculate_yuri
from yuri_state import YuriChessState

do_debug = False

def print_info(str):
	print("info string " + str)

def init_board(_, state):
	print_info("Resetting the board")
	state.current_board = chess.Board()
	print("readyok")

def debug(command, state):
	state.do_debug = ("on" in command)

def setup_pos(command, state):
	if "position" != command[0]:
		print_info("Weird, this command should start with 'position'. Instead, it's {}.".format(command))

	curr_idx = 1

	if "startpos" == command[curr_idx]:
		curr_idx += 1
		state.current_board = chess.Board()
	elif "fen" == command[curr_idx]:
		state.current_board.set_board_fen(command[curr_idx + 1])
		curr_idx += 2

	if "moves" in command:
		if "moves" != command[curr_idx]:
			print_info("Weird, expected 'moves' at position {}.".format(curr_idx))
		curr_idx += 1

		for move in command[curr_idx:]:
			state.current_board.push_uci(move)

def best_move(legal_moves, evaluation_func, min_or_max):
	return min_or_max(legal_moves, key=evaluation_func)

def print_best_move(_, state):
	print("bestmove " + state.last_best_move["NameUCI"])

def move_would_draw(current_board, move_name):
	algebraic_name = current_board.san(chess.Move.from_uci(move_name))
	current_board.push_uci(move_name)
	will_draw = current_board.can_claim_draw() or current_board.is_stalemate() or current_board.is_repetition() or current_board.is_fifty_moves()
	if will_draw:
		print_info("Move {} ({}) will {}draw because{}{}{}".format(move_name, algebraic_name, "" if will_draw else "not ", " repetition" if current_board.can_claim_threefold_repetition() else "", " fifty move rule" if current_board.can_claim_fifty_moves() else "", " stalemate" if current_board.is_stalemate() else ""))
	current_board.pop()
	return will_draw

def move_to_yuri(move, board):
	yuricalc = calculate_yuri(board.san(move))
	yuricalc["NameUCI"] = move.uci()
	return yuricalc

def resolve_tiebreaker(selected_best_move, yuri_moves, eval_func, backup_eval_func):
	tied_for_best = list(filter(lambda x: eval_func(x) == eval_func(selected_best_move), yuri_moves))
	if len(tied_for_best) < 2:
		print_info("No tiebreaker to be done here.")
		return selected_best_move
	print_info("Resolving tiebreaker between {} moves: {}".format(len(tied_for_best), " ".join(map(lambda x: x["Name"], tied_for_best))))

	# so the backup tiebreaker works, but it tends to lead to loops because it likes to pick the same two moves over and over
	# I think the modulo method is better because it's more sensitive to board states (a slight change in legal moves or the exact move being played tends to completely change the output)
	# Since I already wrote the backup stuff, I've decided to use the backup eval function to help "seed" the modulo so it gets to be part of the outcome.
	# Is that not yuri?

	#new_best_move = best_move(tied_for_best, backup_eval_func)
	#tied_for_tiebreaker_best = list(filter(lambda x: backup_eval_func(x) == backup_eval_func(new_best_move), yuri_moves))
	#if len(tied_for_tiebreaker_best) < 2:
	#	print_info("Tiebreaker worked!")
	#	return new_best_move

	#print_info("Resolving double tiebreaker between {} moves: {}".format(len(tied_for_tiebreaker_best)," ".join(map(lambda x: x["Name"], tied_for_tiebreaker_best)) ))

	return tied_for_best[int(eval_func(selected_best_move) * backup_eval_func(selected_best_move)) % len(tied_for_best)]

def search_moves(command, state):
	if "go" != command[0]:
		print_info("Weird, this command should start with 'go'. Instead, it's {}.".format(command))

	yuried_moves = list(filter(lambda x: move_would_draw(state.current_board, x["NameUCI"]) == False, map(lambda m: move_to_yuri(m, state.current_board), state.current_board.legal_moves)))

	if not yuried_moves:
		print_info("All moves would draw or something! Playing the gayest move regardless.")
		yuried_moves = list(map(lambda m: move_to_yuri(m, state.current_board), state.current_board.legal_moves))

	if "searchmoves" in command:
		yuried_moves = [x for x in yuried_moves if x["NameUCI"] in command]

	for move in yuried_moves:
		print("info currmove {} score cp {}".format(move["Name"], state.current_eval_func(move)))

	first_best_move = best_move(yuried_moves, state.current_eval_func)

	state.last_best_move = resolve_tiebreaker(first_best_move, yuried_moves, state.current_eval_func, state.backup_eval_func)

	print_info("I think the best move is {} with {} points and {} backup points.".format(state.last_best_move["Name"], state.current_eval_func(state.last_best_move), state.backup_eval_func(state.last_best_move)))

	if (state.current_board.is_en_passant(state.last_best_move)):
		print_info("Holy hell.\n")

	if "infinite" not in command:
		print_best_move(command, state)	

def parse_check(checkstr):
	if checkstr.casefold() == "false":
		return False
	return True

def set_option(command, state):
	for i, com in enumerate(command):
		if com == "YuriAttribute":
			target_attribute = command[i+2]
			state.current_eval_func = lambda x: x[target_attribute]
			state.backup_eval_func = lambda x: x["Bonus"+target_attribute]
			print_info("Evaluating moves based on {}.".format(target_attribute))
		if com == "MaximizeYuri":
			should_max = parse_check(command[i+2])
			state.min_or_max = max if should_max else min
			print_info("{} the appropriate yuri attribute.".format("Maximizing" if should_max else "Minimizing"))

def uci_intro(_, __):
	print("id name YuriFish\n"
	   "id author The Internet's Beloved Princess Grace\n"
	   "option name YuriAttribute type combo default MaxYuri var Sum var Gayness var Boldness var Commitment var Lewdness\n"
	   "option name MaximizeYuri type check default true\n"
	   "nuciok"),

def no_op(_, __):
	pass

uci_commands = {
	"uci": uci_intro,
	"position": setup_pos,
	"isready": init_board,
	"ucinewgame": init_board,
	"debug": debug,
	"stop": print_best_move,
	"go": search_moves,
	"setoption": set_option,
	"register": no_op,
	"xboard": no_op,
	"": no_op
}

print_info("Welcome to YuriChess!")

state = YuriChessState()

for line in sys.stdin:
	command = line.strip()
	#print_info(command)
	if "quit" in command:
		break

	split_command = command.split()
	
	try:
		uci_commands[split_command[0]](split_command, state)
	except KeyError:
		print_info("Got command {} that I didn't know what to do with.".format(command))

	sys.stdout.flush()

print("Thanks for yuri!")